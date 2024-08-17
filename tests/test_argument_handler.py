import unittest
from unittest.mock import patch, MagicMock
import os.path as _p
import ast
from io import StringIO
from argparse import Namespace
import src.nixglhost


_script_path = src.nixglhost.__file__
_script_filename = _p.split(_script_path)[-1]
_script_name = _p.splitext(_p.split(_script_path)[-1])[0]


class _MockedSystemExitException(Exception):
    pass

class TestScriptArgParser(unittest.TestCase):
    '''
    HACK: if you want to test the logic in the if __name__ == '__main__' block,
    you can use something like runpy, which loads the module and lets you
    execute the __main__ block. But this doesn't let you mock out the main()
    function *called by* the __main__ block in order to check the args.

    So in order to ensure we can do both, we will manipulate the AST and eval():
    - hack main(args) so it simply prints args to a string, to check its shape
    - hack the __main__ block so we can inject custom sys.argv as test cases
    - change the __main__ block to `if True` so it runs on eval()
    - hack sys.exit so we can run multiple tests
    '''

    def _run_nixglhost_script(self, *cli_args):

        mocked_sys_argv = list(cli_args)

        class CodeTransformer(ast.NodeTransformer):
            def visit_FunctionDef(self, node):
                if node.name == 'main':
                    # override main(args) to simply print out args
                    # so we can capture it and check its shape
                    node.body = ast.parse('print(repr(args), file=sys.stderr)').body
                return node
        
            def visit_If(self, node):
                # change
                #     if __name__ == "__main__":
                # into
                #     if True:
                if (isinstance(node.test, ast.Compare) and
                    isinstance(node.test.left, ast.Name) and
                    node.test.left.id == '__name__' and
                    isinstance(node.test.comparators[0], ast.Constant) and
                    node.test.comparators[0].value == '__main__'):
                    node.test = ast.Constant(value=True)
                    # hack sys.argv
                    sys_argv_mod = ast.parse(f"import sys; sys.argv = {repr(mocked_sys_argv)}").body
                    node.body = sys_argv_mod + node.body
                return node

        with open(src.nixglhost.__file__, "r") as file:
            source = file.read()

        code_ast = ast.parse(source)
        transformed_ast = CodeTransformer().visit(code_ast)
        ast.fix_missing_locations(transformed_ast)
        compiled_code = compile(transformed_ast, filename="<ast>", mode="exec")
        exec(compiled_code, {})

    @patch('sys.exit', side_effect=_MockedSystemExitException('sys.exit'))
    def test_main(self, mocked_system_exit):

        def _assert_call_output_contains(command_string, test_string):

            with patch('sys.stderr', new_callable=StringIO) as mocked_stderr:
                with self.assertRaises(_MockedSystemExitException) as context:
                    self._run_nixglhost_script(*command_string.split())
                self.assertIn(test_string, mocked_stderr.getvalue())

        _assert_call_output_contains('nixglhost',
                                     'Please set the NIX_BINARY')

        _assert_call_output_contains('nixglhost mybinary',
                                     repr(Namespace(
                                         driver_directory=None,
                                         print_ld_library_path=False,
                                         NIX_BINARY='mybinary',
                                         ARGS=[],
                                     )))

        _assert_call_output_contains('nixglhost -p',
                                     repr(Namespace(
                                         driver_directory=None,
                                         print_ld_library_path=True,
                                         NIX_BINARY=None,
                                         ARGS=[],
                                     )))

        _assert_call_output_contains('nixglhost -d blah mybinary -d -p',
                                     repr(Namespace(
                                         driver_directory='blah',
                                         print_ld_library_path=False,
                                         NIX_BINARY='mybinary',
                                         ARGS=['-d', '-p'],
                                     )))

        _assert_call_output_contains('nixglhost mybinary -a -b -c',
                                     repr(Namespace(
                                         driver_directory=None,
                                         print_ld_library_path=False,
                                         NIX_BINARY='mybinary',
                                         ARGS=['-a', '-b', '-c'],
                                     )))

        _assert_call_output_contains('nixglhost mybinary -- -a -b -c',
                                     repr(Namespace(
                                         driver_directory=None,
                                         print_ld_library_path=False,
                                         NIX_BINARY='mybinary',
                                         ARGS=['-a', '-b', '-c'],
                                     )))
