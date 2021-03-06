import unithelper
from bc.validator import ValidError
from bc.validator import Validate as V

class Test(unithelper.TestCase):
	def test_basic(self):
		"""Check basic types"""

		tmpl = V({
			'a': V(int),
			'b': V(basestring),
			'c': V(list),
			'd': V(dict),
			'e': V(tuple),
		})
		data = { 'a': 1, 'b': 'X', 'c': [ 1 ], 'd': { 'dd':1 }, 'e': (1,2,3) }
		res = tmpl.check(data)
		self.assertEqual(data, res)

		tmpl = V(int)
		self.assertEqual(1, tmpl.check(1))

		tmpl = V(basestring)
		self.assertEqual('x', tmpl.check('x'))

		tmpl = V(list)
		self.assertEqual([1], tmpl.check([1]))

		tmpl = V(dict)
		self.assertEqual({'a':1}, tmpl.check({'a':1}))


	def test_basic_list(self):
		"""Check list validation"""

		tmpl = V([ V(int) ])
		data = [ 1, 2, 3, 4, 5 ]
		res = tmpl.check(data)
		self.assertEqual(data, res)

		tmpl = V([ V(basestring), V(int) ])
		data = [ 'x', 1, 2, 3, 4, 5 ]
		res = tmpl.check(data)
		self.assertEqual(data, res)


	def test_default(self):
		"""Check default= option"""

		data = {'a':1}

		tmpl = V({ 'a': V(int), 'b': V(int, default = 10) })
		res = tmpl.check(data)
		self.assertEqual({'a':1,'b':10}, res)

		tmpl = V({ 'a': V(int), 'b': V(basestring,default='x') })
		res = tmpl.check(data)
		self.assertEqual({'a':1,'b':'x'}, res)

		tmpl = V({ 'a': V(int), 'b': V(dict, default={'b1':1,'b2':2 }) })
		res = tmpl.check(data)
		self.assertEqual({'a':1,'b':{'b1':1, 'b2':2}}, res)

		tmpl = V({ 'a': V(int), 'b': V(basestring, default=1) })
		self.assertRaises(ValidError, lambda: tmpl.check(data))


	def test_required_false(self):
		"""Check required=False option"""

		tmpl = V({'a':V(int),'b':V(int, required=False)})

		data = {'a':1}
		res = tmpl.check(data)
		self.assertEqual({'a':1,'b':None}, res)

		data = {'a':1,'b':2}
		res = tmpl.check(data)
		self.assertEqual({'a':1,'b':2}, res)

		tmpl = V({
			'a': V(int),
			'b': V({
				'b1': V(int)
			}, required=False)
		})
		self.assertEqual({'a':1,'b':None}, tmpl.check({'a':1}))


	def test_required_true(self):
		"""Check required=True option"""
		tmpl = V({'a':V(int),'b':V(int, required=True)})
		data = {'a':1}
		self.assertRaises(ValidError, lambda: tmpl.check(data))


	def test_maxmin(self):
		"""Check min= max= options"""

		tmpl = V(int, max=10)
		self.assertEqual(5, tmpl.check(5))

		tmpl = V(int, min=3, max=10)
		self.assertEqual(5, tmpl.check(5))

		tmpl = V(int, min=3, max=10)
		self.assertRaises(ValidError, lambda: tmpl.check(2))

		tmpl = V(int, min=3, max=10)
		self.assertRaises(ValidError, lambda: tmpl.check(11))


	def test_variant(self):
		"""Check variants"""

		tmpl = V( ( V(int), V(basestring) ) )
		self.assertEqual('x', tmpl.check('x'))
		self.assertEqual(1,   tmpl.check(1))
		self.assertRaises(ValidError, lambda: tmpl.check([1]))

		tmpl = V({
			'a': V( ( V(int), V(basestring) ) )
		})
		self.assertEqual({'a':'x'}, tmpl.check({'a':'x'}))
		self.assertEqual({'a':1},   tmpl.check({'a':1}))
		self.assertRaises(ValidError, lambda: tmpl.check({'a':[1]}))


	def test_unknown(self):
		"""Check unknown"""

		tmpl = V({'a':V(int)}, unknown=True)
		data = { 'a': 1 }
		self.assertEqual(data, tmpl.check(data))

		tmpl = V({'a':V(int)}, unknown=True)
		data = { 'a': 1, 'b': 2 }
		self.assertEqual(data, tmpl.check(data))

		tmpl = V({'a':V(int)}, unknown=False)
		data = { 'a': 1, 'b': 2 }
		self.assertRaises(ValidError, lambda: tmpl.check({'a':[1]}))


	def test_unspecified(self):
		"""Check unspecified"""

		tmpl = V({ 'a':V(int), 'b':V(int, required=False), 'c':V(int, required=False) })
		data = { 'a': 1, 'b': None, 'c': None }
		self.assertEqual(data, tmpl.check(data))

		tmpl = V({ 'a':V(int), 'b':V(int, required=False), 'c':V(int, required=False) }, drop_optional=True)
		data = { 'a': 1 }
		self.assertEqual(data, tmpl.check(data))
