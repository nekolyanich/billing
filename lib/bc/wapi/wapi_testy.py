__version__ = '1.0'

from bc import jsonrpc
from bc import log

LOG = log.logger("wapi.testy")

@jsonrpc.method(auth=0)
def test(params):
	return jsonrpc.result({'status':'ok'})
