#
# database.py
#
# Copyright (c) 2012-2013 by Alexey Gladkov
# Copyright (c) 2012-2013 by Nikolay Ivanov
#
# This file is covered by the GNU General Public License,
# which should be included with billing as the file COPYING.
#
import os
import re
import time
import uuid
import inspect
import logging

from bc import config
from bc import hashing

import psycopg2
from psycopg2 import extensions
from psycopg2 import extras
from psycopg2 import errorcodes
from psycopg2 import pool

MIN_OPEN_CONNECTIONS = 1
MAX_OPEN_CONNECTIONS = 20

# Backend exceptions:
OperationalError = psycopg2.OperationalError
DatabaseError    = psycopg2.DatabaseError

# Backend methods
DBCursor  = extras.RealDictCursor

# Backend status
TRANSACTION_STATUS_IDLE       = extensions.TRANSACTION_STATUS_IDLE
TRANSACTION_STATUS_INERROR    = extensions.TRANSACTION_STATUS_INERROR

LOG = logging.getLogger("database")

class DBError(Exception):
	"""The base class for database exceptions that our code throws"""

	def __init__(self, error, *args):
		Exception.__init__(self, unicode(error).format(*args) if len(args) else unicode(str(error)))


def get_strerror(exc):
	if exc.pgcode == None:
		return "Code=None: Database error"

	return "Code={0}: {1}: {2}".format(
		exc.pgcode,
		errorcodes.lookup(exc.pgcode[:2]),
		errorcodes.lookup(exc.pgcode)
	)


def get_host(dbtype, key=None):
	"""Returns database server"""

	conf = config.read()

	if key != None:
		data = config.subdict(conf['database']['shards'], field='weight')
		ring = hashing.HashRing(data.keys(), data)
		return conf['database']['shards'][ring.get_node(key)]['server']
	elif dbtype == 'local':
		for shard in conf['database']['shards'].itervalues():
			if shard['local'] == True:
				return shard['server']
	elif dbtype == 'global':
		return conf['database']['server']


def sqldbg(qs):
	if os.environ.get('BILLING_SQL_DESCRIBE', False):
		LOG.debug("SQL: " + qs)


def runover(arr):
	stack = [ iter(arr) ]
	while len(stack) > 0:
		for x in stack[-1]:
			if isinstance(x,(list,tuple)):
				stack.append(iter(x))
				break
			if inspect.isgenerator(x):
				stack.append(x)
				break
			yield x
		else:
			stack.pop()


def _sqllist(x, s):
	if s:
		return sorted(x)
	return x


def sqlcmd(a, delim=' '):
	return delim.join(runover(a))


class DBPool(object):

	def __init__(self):
		self._CONNECTIONS = {}


	def get_connection(self, dbhost=None, dbname=None, dbuser=None, dbpass=None, dbtype='global', primarykey=None):
		"""Returns free connection"""

		conf = config.read()

		conn = {}
		conn['dbuser'] = dbuser or conf['database']['user']
		conn['dbpass'] = dbpass or conf['database']['pass']
		conn['dbname'] = dbname or conf['database']['name']
		conn['dbhost'] = dbhost or get_host(dbtype, primarykey)

		if not conn['dbhost']:
			raise DBError("Database host name is not specified")

		conn['key'] = "{0}@{1}/{2}".format(conn['dbuser'], conn['dbhost'], conn['dbname'])

		if conn['key'] not in self._CONNECTIONS:
			self._CONNECTIONS[conn['key']] = pool.ThreadedConnectionPool(

				# Pool params
				MIN_OPEN_CONNECTIONS,
				MAX_OPEN_CONNECTIONS,

				# Connection params
				host     = conn['dbhost'],
				database = conn['dbname'],
				user     = conn['dbuser'],
				password = conn['dbpass']
			)
		conn['socket'] = self._CONNECTIONS[conn['key']].getconn()

		return conn


	def free_connection(self, conn):
		conn['socket'].reset()
		self._CONNECTIONS[conn['key']].putconn(conn['socket'])


class DBQuery(object):
	cursor = None

	def __init__(self, cursor, autocommit, fmt, *args):
		self.cursor = cursor
		self.autocommit = autocommit
		try:
			if self.autocommit:
				cursor.execute("START TRANSACTION")
			self.cursor.execute(fmt, *args)
		except psycopg2.Error as e:
			self.cursor.execute("ROLLBACK")
			self.cursor.close()
			self.cursor = None
			raise e

	def close(self):
		if not self.cursor or self.cursor.closed:
			return
		try:
			self.cursor.fetchall()
			if self.autocommit:
				self.cursor.execute("COMMIT")
		finally:
			self.cursor.close()
			self.cursor = None

	def __iter__(self):
		if not self.cursor or self.cursor.closed:
			return
		try:
			for o in self.cursor:
				yield o
		finally:
			self.close()

	def one(self):
		if not self.cursor or self.cursor.closed:
			return None
		try:
			return self.cursor.fetchone()
		finally:
			self.close()

	def all(self):
		if not self.cursor or self.cursor.closed:
			return []
		try:
			return self.cursor.fetchall()
		finally:
			self.close()


DB = DBPool()

class DBConnect(object):
	def __init__(self, dbhost=None, dbname=None, dbuser=None, dbpass=None, dbtype='global', primarykey=None, autocommit=True):
		self._conn = DB.get_connection(dbhost, dbname, dbuser, dbpass, dbtype, primarykey)
		for n in [ 'dbhost', 'dbname', 'dbuser', 'dbpass' ]:
			self.__dict__[n] = self._conn[n]

		self.autocommit = bool(autocommit)
		self._curlist = []
		self.state = 0


	def __enter__(self):
		return self


	def __exit__(self, exc_type, exc_value, traceback):
		conn_status = self.connect().get_transaction_status()
		cursor_cmd = None

		if conn_status != TRANSACTION_STATUS_IDLE:
			cursor_cmd = (conn_status == TRANSACTION_STATUS_INERROR) \
				and "ROLLBACK" \
				or  "COMMIT"

		for cur in self._curlist:
			if cur.closed:
				continue
			if cursor_cmd:
				cur.execute(cursor_cmd)
			cur.close()

		DB.free_connection(self._conn)
		return False


	def connect(self):
		"""Returns database connection
		"""
		return self._conn['socket']


	def cursor(self):
		"""Returns database cursor
		"""
		if not self._curlist:
			self._curlist.append(DBCursor(self.connect()))

		elif self._curlist[0].closed:
			self._curlist[0] = DBCursor(self.connect())

		return self._curlist[0]


	def in_transaction(self):
		return self.connect().get_transaction_status() != TRANSACTION_STATUS_IDLE


	def begin(self):
		"""Begins a new transaction block
		"""
		if self.in_transaction():
			return
		self.cursor().execute("START TRANSACTION")


	def commit(self):
		"""Commits the current transaction
		"""
		if not self.in_transaction():
			return
		self.cursor().execute("COMMIT")


	def savepoint(self, point, release=False):
		"""Establishes (or removes) a savepoint within the current transaction

		A savepoint is a special mark inside a transaction that allows all commands
		that are executed after it was established to be rolled back, restoring
		the transaction state to what it was at the time of the savepoint.

		Parameters:

		point:     the name of the savepoint;
		release:   destroys a savepoint previously defined.
		"""
		if not self.in_transaction():
			return
		qs = (release) and "RELEASE SAVEPOINT %s" or "SAVEPOINT %s"
		self.cursor().execute(qs, point)


	def rollback(self, point=None):
		"""Rolls back whole (or part) transaction

		Function rolls back all commands that were executed after
		the savepoint was established if 'point' parameter given.

		Parameters:

		point:   the name of the savepoint.
		"""
		if not self.in_transaction():
			return
		if point != None:
			self.cursor().execute("ROLLBACK TO SAVEPOINT %s", point)
			return
		self.cursor().execute("ROLLBACK")


	def execute(self, fmt, *args):
		"""Exetutes SQL command
		"""
		self.begin()
		try:
			self.cursor().execute(fmt, *args)

		except psycopg2.Error as e:
			if self.autocommit:
				self.rollback()
			raise e

		if self.autocommit:
			self.commit()


	def query(self, fmt, *args):
		"""Queries the database and returns DBCursor with result
		"""
		self._curlist = filter(lambda x: x.closed, self._curlist)

		cur = DBCursor(self.connect())
		self._curlist.append(cur)

		return DBQuery(cur, self.autocommit, fmt, *args)


	def sql_update(self, query, sort=False):
		"""Converts mongo-like dictionary to SET condition for UPDATE statement
		"""
		bit_ops = {
			'and':    lambda x: '&'  + arg(x),
			'or':     lambda x: '|'  + arg(x),
			'xor':    lambda x: '^'  + arg(x),
			'rshift': lambda x: '>>' + arg(x),
			'lshift': lambda x: '<<' + arg(x),
		}
		func_ops = {
			'$field': lambda x: (str(x),),
			'$abs':   lambda x: ('ABS('   + arg(x) + ')',),
			'$ceil':  lambda x: ('CEIL('  + arg(x) + ')',),
			'$crc32': lambda x: ('CRC32(' + arg(x) + ')',),
			'$floor': lambda x: ('FLOOR(' + arg(x) + ')',),
			'$mod':   lambda x: ('MOD('   + arg(x[0]) + ',' + arg(x[1]) + ')',),
			'$round': lambda x: (len(x) == 2 and 'ROUND(' + arg(x[0]) + ',' + arg(x[1]) + ')' or 'ROUND(' + arg(x[0]) + ')',),
		}
		ops = {
			'$bit':    lambda x:   bit_ops[x[0]](x[1]),
			'$set':    lambda x,y: x + "=" + arg(y),
			'$dec':    lambda x,y: x + "=" + x + "-" + arg(y),
			'$inc':    lambda x,y: x + "=" + x + "+" + arg(y),
			'$div':    lambda x,y: x + "=" + x + "/" + arg(y),
			'$mult':   lambda x,y: x + "=" + x + "*" + arg(y),
			'$concat': lambda x,y: x + "=CONCAT(" + x + "," +  self.literal(y) + ")",
		}
		def arg(x):
			if isinstance(x, basestring):
				return self.literal(x)
			if isinstance(x, tuple):
				return x[0]
			return str(x)

		def resole_op(arg):
			k,v = arg.popitem()
			if isinstance(v, dict):
				return func_ops[k](resole_op(v))
			return func_ops[k](v)

		res = []
		for op in _sqllist(query.keys(), sort):
			cond = query[op]
			if op in [ '$set', '$inc', '$dec', '$div', '$mult' ]:
				for n,v in cond.iteritems():
					if isinstance(v, dict):
						res.append(ops[op](n, resole_op(v)))
					else:
						res.append(ops[op](n, v))
			elif op == '$concat':
				res.extend(map(lambda x: ops[op](x[0],x[1]),cond.iteritems()))
			elif op == '$bit':
				res.extend(map(lambda x: x[0]+"="+x[0]+"".join(map(ops[op],x[1].iteritems())),cond.iteritems()))
			else:
				res.append(op + "=" + self.literal(cond))

		return self._delim(_sqllist(res, sort),",")


	def sql_where(self, query, sort=False):
		"""Converts mongo-like dictionary to SQL WHERE statement
		"""
		def sql_bool(x):
			if x == None:
				return 'NULL'
			return str(bool(x))

		def sql_optimize_operation(op, value):
			if op == '$eq':
				if isinstance(value, bool) or value == None:
					return '$is'
				if isinstance(value, list):
					return '$in'
			if op == '$ne':
				if isinstance(value, bool) or value == None:
					return '$notis'
				if isinstance(value, list):
					return '$nin'
			return op

		def sql_quote(op, value):
			if op in ['$is','$notis']:
				return sql_bool(value)

			if op in ['$in','$nin']:
				return ",".join(map(self.literal, value))

			if isinstance(value, dict) and op in ['$gt','$ge','$lt','$le','$eq','$ne']:
				if '$field' not in value:
					raise ValueError('Unsupported value type')
				return value['$field']

			return self.literal(value)

		concatenation = {
			'$and': "AND",
			'$or':  "OR",
		}
		operation = {
			'$gt':     lambda x,y: [ x, ">"          , y ],
			'$ge':     lambda x,y: [ x, ">="         , y ],
			'$lt':     lambda x,y: [ x, "<"          , y ],
			'$le':     lambda x,y: [ x, "<="         , y ],
			'$eq':     lambda x,y: [ x, "="          , y ],
			'$ne':     lambda x,y: [ x, "!="         , y ],
			'$is':     lambda x,y: [ x, "IS"         , y ],
			'$notis':  lambda x,y: [ x, "IS NOT"     , y ],
			'$regex':  lambda x,y: [ x, "REGEXP"     , y ],
			'$nregex': lambda x,y: [ x, "NOT REGEXP" , y ],
			'$like':   lambda x,y: [ x, "LIKE"       , y ],
			'$nlike':  lambda x,y: [ x, "NOT LIKE"   , y ],
			'$in':     lambda x,y: [ x, "IN ("       , y, ")" ],
			'$nin':    lambda x,y: [ x, "NOT IN ("   , y, ")" ],
		}
		result = []
		for name in _sqllist(query.keys(), sort):
			conditions = query[name]

			if name == '$not':
				result.append([ "NOT (", self.sql_where(conditions, sort), ")" ])
			elif name in concatenation:
				a = map(lambda x: [ "(", self.sql_where(x, sort), ")" ], conditions)
				result.append([ "(", self._delim(a, concatenation[name]), ")" ])
			elif isinstance(conditions, dict):
				for o, value in conditions.iteritems():
					o = sql_optimize_operation(o, value)
					v = sql_quote(o,value)
					result.append(operation[o](name,v))
			else:
				o = sql_optimize_operation('$eq', conditions)
				v = sql_quote(o, conditions)
				result.append(operation[o](name, v))

		return self._delim(_sqllist(result, sort), concatenation['$and'])


	def escape(self, string):
		"""Escapes any special characters
		"""
		if isinstance(string, (basestring, unicode)):
			return re.sub(r'([\'\"\\])', r'\\\1', str(string))
		return str(string)
		#return self.connect().escape_string(str(string))


	def literal(self, string):
		"""Returns SQL string literal

		If 'string' is a single object, returns an SQL literal as a string.
		If 'string' is a non-string sequence, the items of the sequence are
		converted and returned as a sequence.
		"""
		return "'{0}'".format(self.escape(string))


	def _delim(self, arr, delim=', '):
		n = len(arr) - 1
		for i in xrange(0, n):
			yield arr[i]
			yield delim
		yield arr[n]


	def _genlist(self, arg, default):
		if isinstance(arg, list) and arg:
			return self._delim(arg)
		elif isinstance(arg, dict) and arg:
			return self._delim(map(lambda x: x[0]+' as '+x[1], arg.iteritems()))
		else:
			return [ default ]


	def delete(self, table, spec=None, returning=None):
		"""Removes a document(s) from this table

		Parameters:

		table:     specify a table name;

		spec:      a dictionary specifying the documents to be removed;

		returning: The optional argument that causes delete() to compute and
		           return value(s) based on each row actually updated.
		           The syntax of the 'returning' list is identical to that
		           of the output list of find().
		"""

		fmt = [ "DELETE FROM", table ]

		if isinstance(spec, dict) and len(spec) > 0:
			fmt.extend([ "WHERE", self.sql_where(spec) ])

		need_return = isinstance(returning, (dict, list))

		if need_return:
			fmt.extend([ "RETURNING", len(returning) > 0 and self._genlist(returning, '*') or '*' ])

		qs = " ".join(runover(fmt))
		sqldbg(qs)

		if need_return:
			return self.query(qs)
		self.execute(qs)


	def insert(self, table, document, returning=None):
		"""Inserts a document(s) into this table

		Parameters:

		table:     specify a table name;

		document:  a document to be inserted.

		returning: The optional argument that causes insert() to compute and
		           return value(s) based on each row actually updated.
		           The syntax of the 'returning' list is identical to that
		           of the output list of find().
		"""

		if not isinstance(document, (dict, list)):
			raise TypeError("Wrong type of 'document': {1}".format(type(document).__name__))

		if len(document) == 0:
			raise ValueError("The 'document' should not be empty")

		if isinstance(document, (dict)):
			document = [ document ]

		keys = sorted(document[0].keys())
		fmt = [ "INSERT INTO", table, "(", self._delim(keys), ")", "VALUES" ]

		for o in document:
			# This is a simple protection against errors.
			# We add value only by the keys from the first element.
			fmt.extend([ "(", self._delim(map(lambda x: self.literal(o[x]), keys)), ")", "," ])
		fmt.pop()

		need_return = isinstance(returning, (dict, list))

		if need_return:
			fmt.extend([ "RETURNING", len(returning) > 0 and self._genlist(returning, '*') or '*' ])

		qs = " ".join(runover(fmt))
		sqldbg(qs)

		if need_return:
			return self.query(qs)
		self.execute(qs)


	def update(self, tables, spec, document, returning=None):
		"""Updates a document(s) in this table(s)

		Parameters:

		tables:   specify a table name or list of names;

		spec:     a dict or SON instance specifying elements which
		          must be present for a document to be updated;

		document: a dict or SON instance specifying the document to be used
		          for the update;

		returning: The optional argument that causes update() to compute and
		           return value(s) based on each row actually updated.
		           The syntax of the 'returning' list is identical to that
		           of the output list of find().
		"""

		for n,o in [ ('document',document), ('spec',spec) ]:
			if not isinstance(o, dict):
				raise TypeError("Wrong type of '{0}': {1}".format(n, type(o).__name__))

		if len(document) == 0:
			raise ValueError("The 'document' should not be empty")

		fmt = [ "UPDATE", self._genlist(tables, tables), "SET", self.sql_update(document) ]
		if len(spec) > 0:
			fmt.extend([ "WHERE", self.sql_where(spec) ])

		need_return = isinstance(returning, (dict, list))

		if need_return:
			fmt.extend([ "RETURNING", len(returning) > 0 and self._genlist(returning, '*') or '*' ])

		qs = " ".join(runover(fmt))
		sqldbg(qs)

		if need_return:
			return self.query(qs)
		self.execute(qs)


	def find(self, tables, spec=None, fields=None, sort=None, skip=0, limit=0, lock=None, nowait=False):
		"""Query the database

		The spec argument is a prototype document that all results must match.
		Returns an instance of Cursor corresponding to this query.

		Parameters:

		spec:   a SON object specifying elements which must be present
		        for a document to be included in the result set;

		fields: a list of field names that should be returned
		        or a dict specifying the fields to return;

		skip:   the number of documents to omit (from the start of the result set)
		        when returning the results;

		limit:  the maximum number of results to return;

		sort:   a list of (key, direction) pairs specifying the sort order
		        for this query.
		"""
		fmt = [ "SELECT", self._genlist(fields, '*'), "FROM", self._genlist(tables, tables) ]
		if isinstance(spec, dict):
			fmt.extend([ "WHERE", self.sql_where(spec) ])
		if sort != None and len(sort) > 0:
			fmt.extend([ "ORDER BY", self._genlist(sort, None) ])
		if limit > 0:
			fmt.extend([ "LIMIT", str(limit) ])
		if skip > 0:
			fmt.extend([ "OFFSET", str(skip) ])

		if lock != None:
			if lock == 'update':
				fmt.append("FOR UPDATE")

			elif lock == 'share':
				# Another syntax in MySQL: LOCK IN SHARE MODE
				fmt.append("FOR SHARE")

			# Unsupported in MySQL
			if nowait:
				fmt.append("NOWAIT")

		qs = " ".join(runover(fmt))
		sqldbg(qs)

		return self.query(qs)


	def find_one(self, *args, **kwargs):
		"""Gets a single document from the database

		All arguments to find() are also valid arguments for find_one(),
		although any limit argument will be ignored. Returns a single document,
		or None if no matching document is found.
		"""
		return self.find(*args, **kwargs).one()


	def find_all(self, *args, **kwargs):
		"""Gets a all documents as list from the database

		All arguments to find() are also valid arguments for find_all().
		"""
		return self.find(*args, **kwargs).all()
