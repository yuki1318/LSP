from .process import add_extension_if_missing
from .process import start_server
from .test_session import TEST_CONFIG
from copy import deepcopy
from unittest import TestCase
import os


class ProcessModuleTest(TestCase):

    def test_add_extension_if_missing(self) -> None:
        if os.name != "nt":
            self.skipTest("only useful for windows")
        # TODO: More extensive tests.
        args = add_extension_if_missing(["cmd"])
        self.assertListEqual(args, ["cmd"])

    def working_dir(self) -> str:
        return os.path.dirname(__file__)

    def test_start_server_failure(self) -> None:
        with self.assertRaises(FileNotFoundError):
            start_server(
                server_binary_args=["some_file_that_most_definitely_does_not_exist", "a", "b", "c"],
                working_dir=self.working_dir(),
                env={},
                attach_stderr=False)

    def test_start_server(self) -> None:
        config = deepcopy(TEST_CONFIG)  # Don't modify the original dict.
        if os.name == "nt":
            config.binary_args = ["cmd.exe"]
        else:
            config.binary_args = ["ls"]
        config.binary_args.extend(["a", "b", "c"])
        popen = start_server(
            server_binary_args=config.binary_args,
            working_dir=self.working_dir(),
            env={},
            attach_stderr=False)
        self.assertIsNotNone(popen)
        assert popen
        args = list(map(str, popen.args[1:]))  # type: ignore
        self.assertListEqual(args, ["a", "b", "c"])
