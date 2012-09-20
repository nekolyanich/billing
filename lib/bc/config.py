#!/usr/bin/python

import re
import json
import cStringIO

from bc import utils

CONFIG = None
CONFIG_FILE = '/etc/billing.conf'

_TEMPLATE_CONFIG = {
	# Logger configuration
	'logging': {
		'type': 'syslog',
		'level': 'error',
		'logdir': '/var/log',
		'logsize': '30Mb',
		'backcount': 3,
		'address': '/dev/log',
		'facility': 'daemon'
	},

	"server": {
		"pidfile": "/tmp/bc-server.pid",
		"workers": 3
	},

	"zone": {
		"local-DC": { "server": "localhost", "weight": 3, "local": True }
	},

	# Database section
	"database": {
		# Database name
		"name": "billing",

		"user": "root",
		"pass": "",

		# Database searver for global collections
		"server": "127.0.0.1",

		# Database servers for sharding
		"shards": {}
	}
}

def read(filename = CONFIG_FILE, inline = None, force = False):
	"""Read system config file"""

	global CONFIG

	if CONFIG and not force:
		return CONFIG

	if isinstance(inline, basestring):
		f = cStringIO.StringIO(inline)
	else:
		f = open(filename, 'r')

	arrconf = []
	while True:
		line = f.readline()
		if not line:
			break

		# Remove trash from line
		line = re.sub(r'(^\s+|\s+$|\s*#.*$)', '', line)

		# Ignore empty string
		if line:
			arrconf.append(line)

	s = re.sub(r'([^,:\{\[])\s+("[^"\\]+":)', r'\1, \2', " ".join(arrconf))

	CONFIG = {}
	return utils.dict_merge(CONFIG, _TEMPLATE_CONFIG, json.loads(s))


def subdict(confdict, field='weight'):
	res = {}
	for k,v in confdict.iteritems():
		res[k] = v[field]
	return res

