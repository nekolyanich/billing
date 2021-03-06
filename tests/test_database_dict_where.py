import unithelper

import unittest2 as unittest
from bc import database
from bc.database import sqlcmd


class Test(unithelper.DBTestCase):
	@unittest.skipUnless(unithelper.haveDatabase(), True)
	def test_short_form(self):
		"""Check syntax statment short form for WHERE statment in UPDATE"""

		testList = [
			(
				{
					'a': 1,
					'b': 2,
					'c': [1,2,3]
				},
				"a = '1' AND b = '2' AND c IN ( '1','2','3' )"
			),
		]
		with database.DBConnect() as db:
			for m,s in testList:
				self.assertEqual(s, sqlcmd(db.sql_where(m, True)))


	@unittest.skipUnless(unithelper.haveDatabase(), True)
	def test_fields(self):
		"""Check '$field' syntax for WHERE statment in UPDATE"""

		testList = [
			(
				{
					'table.a': { '$eq': { '$field': 'table.b' } },
				},
				"table.a = table.b"
			),
			(
				{
					'table0.a': { '$gt': { '$field': 'table1.a' } },
					'table0.b': { '$lt': { '$field': 'table1.b' } },
				},
				"table0.a > table1.a AND table0.b < table1.b"
			),
		]
		with database.DBConnect() as db:
			for m,s in testList:
				self.assertEqual(s, sqlcmd(db.sql_where(m, True)))


	@unittest.skipUnless(unithelper.haveDatabase(), True)
	def test_simple_compare(self):
		"""Check syntax compare for WHERE statment in UPDATE"""

		testList = [
			(
				{
					'a': { '$gt': 1, '$lt': 2 }
				},
				"a < '2' AND a > '1'"
			),
			(
				{
					'a': { '$gt': 1 },
					'b': { '$gt': 2 },
					'c': { '$ne': 3 }
				},
				"a > '1' AND b > '2' AND c != '3'"
			),
			(
				{
					'a': { '$gt': 1, '$le': 2 },
					'b': { '$eq': 3 },
					'c': { '$ne': 4 },
					'd': { '$ge': 5 },
				},
				"a <= '2' AND a > '1' AND b = '3' AND c != '4' AND d >= '5'"
			),
		]
		with database.DBConnect() as db:
			for m,s in testList:
				self.assertEqual(s, sqlcmd(db.sql_where(m, True)))


	@unittest.skipUnless(unithelper.haveDatabase(), True)
	def test_or(self):
		"""Check OR syntax for WHERE statment in UPDATE"""

		testList = [
			(
				{
					'$or': [
						{ 'a': { '$gt': 1 } },
						{ 'a': { '$lt': 2 } },
					]
				},
				"( ( a > '1' ) OR ( a < '2' ) )"
			),
			(
				{
					'a': 1,
					'b': 2,
					'$or': [
						{ 'c': { '$gt': 1 } },
						{ 'c': { '$lt': 2 } },
					]
				},
				"( ( c > '1' ) OR ( c < '2' ) ) AND a = '1' AND b = '2'"
			),
			(
				{
					'$or': [
						{ 'a': { '$gt': 1, '$lt': 2 } },
						{ 'b': { '$eq': 3 } },
					]
				},
				"( ( a < '2' AND a > '1' ) OR ( b = '3' ) )"
			),
			(
				{
					'$or': [
						{ 'a': { '$gt': 1, '$lt': 2 } },
						{ 'b': { '$eq': 3 } },
						{
							'$or': [
								{ 'c': { '$ne': 4 } },
								{ 'd': { '$ge': 5, '$le': 6 } }
							]
						}
					]
				},
				"( ( a < '2' AND a > '1' ) OR ( b = '3' ) OR ( ( ( c != '4' ) OR ( d <= '6' AND d >= '5' ) ) ) )"
			),
		]
		with database.DBConnect() as db:
			for m,s in testList:
				self.assertEqual(s, sqlcmd(db.sql_where(m, True)))


	@unittest.skipUnless(unithelper.haveDatabase(), True)
	def test_and(self):
		"""Check AND syntax for WHERE statment in UPDATE"""

		testList = [
			(
				{
					'$and': [
						{ 'a': { '$gt': 1, '$lt': 2 } },
						{ 'b': { '$eq': 3 } },
					]
				},
				"( ( a < '2' AND a > '1' ) AND ( b = '3' ) )"
			)
		]
		with database.DBConnect() as db:
			for m,s in testList:
				self.assertEqual(s, sqlcmd(db.sql_where(m, True)))


	@unittest.skipUnless(unithelper.haveDatabase(), True)
	def test_not(self):
		"""Check NOT syntax for WHERE statment in UPDATE"""

		testList = [
			(
				{
					'$not': {
						'a': { '$gt': 1, '$lt': 2 },
						'b': { '$eq': 3 },
					}
				},
				"NOT ( a < '2' AND a > '1' AND b = '3' )"
			)
		]
		with database.DBConnect() as db:
			for m,s in testList:
				self.assertEqual(s, sqlcmd(db.sql_where(m, True)))


	@unittest.skipUnless(unithelper.haveDatabase(), True)
	def test_is(self):
		"""Check IS syntax for WHERE statment in UPDATE"""

		testList = [
			(
				{
					'a': True,
					'b': False,
					'c': None
				},
				"a IS True AND b IS False AND c IS NULL"
			),
			(
				{
					'a': { '$eq': True },
					'b': { '$eq': False },
					'c': { '$eq': None },
				},
				"a IS True AND b IS False AND c IS NULL"
			),
			(
				{
					'a': { '$ne': True },
					'b': { '$ne': False },
					'c': { '$ne': None },
				},
				"a IS NOT True AND b IS NOT False AND c IS NOT NULL"
			)
		]
		with database.DBConnect() as db:
			for m,s in testList:
				self.assertEqual(s, sqlcmd(db.sql_where(m, True)))


	@unittest.skipUnless(unithelper.haveDatabase(), True)
	def test_in(self):
		"""Check IN syntax for WHERE statment in UPDATE"""

		testList = [
			(
				{
					'a': [1,2,3]
				},
				"a IN ( '1','2','3' )"
			),
			(
				{
					'a': ['a1','a2','a3']
				},
				"a IN ( 'a1','a2','a3' )"
			),
			(
				{
					'a': ['a\'a','b"b','c;c']
				},
				"a IN ( 'a\\'a','b\\\"b','c;c' )"
			),

		]
		with database.DBConnect() as db:
			for m,s in testList:
				self.assertEqual(s, sqlcmd(db.sql_where(m, True)))


	@unittest.skipUnless(unithelper.haveDatabase(), True)
	def test_like(self):
		"""Check LIKE syntax for WHERE statment in UPDATE"""

		testList = [
			(
				{
					'a': { '$like': 'foo%' }
				},
				"a LIKE 'foo%'"
			),
			(
				{
					'a': { '$nlike': 'foo%' }
				},
				"a NOT LIKE 'foo%'"
			),
		]
		with database.DBConnect() as db:
			for m,s in testList:
				self.assertEqual(s, sqlcmd(db.sql_where(m, True)))


	@unittest.skipUnless(unithelper.haveDatabase(), True)
	def test_regex(self):
		"""Check REGEXP syntax for WHERE statment in UPDATE"""

		testList = [
			(
				{
					'a': { '$regex': 'foo.*$' }
				},
				"a REGEXP 'foo.*$'"
			),
			(
				{
					'a': { '$regex': 'foo\$' }
				},
				"a REGEXP 'foo\\\\$'"
			),
			(
				{
					'a': { '$nregex': 'foo.*' }
				},
				"a NOT REGEXP 'foo.*'"
			),
		]
		with database.DBConnect() as db:
			for m,s in testList:
				self.assertEqual(s, sqlcmd(db.sql_where(m, True)))
