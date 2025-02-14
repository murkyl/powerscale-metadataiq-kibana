#!/usr/bin/env python
# -*- coding: utf8 -*-
# fmt: off
__license__       = "MIT"
__author__        = "Andrew Chung <andrew.chung@dell.com>"
__maintainer__    = "Andrew Chung <andrew.chung@dell.com>"
__email__         = "andrew.chung@dell.com"
__all__ = [
    "parse",
]
# fmt: on
import optparse
import os
import re
import sys
import zipfile
import helpers.constants as constants

ENV_PREFIX = re.sub("[^a-zA-Z0-9]", "_", constants.PROGRAM_NAME.upper())
USAGE = "usage: %prog [OPTION...] input_file <output_file|stdout>"
EPILOG = """
Description
====================

Environment variables
====================
Parameters can be passed in as an environment variable. The environment variable name
is the same as the upper case CLI option with the string prefix: '{pname}_'
For example, if the CLI option is --opt-a then the environment variable would be:
{pname}_OPT_A

Parameter evaluation order
====================
Parameters are process in the following order:
command line options < environment variables

Environment variables have the highest priority while the command line has the least.

Quickstart
====================
python3 translate.py --lang=en input_file.ndjson output_file.ndjson

Return values
====================
0   No errors
1   CLI argument errors
2   Missing Python libraries
3   Error during translation
100 SIGTERM or SIGINT occurred
""".format(
    pname=ENV_PREFIX
)


def add_env_option(parser, env=None):
    if env is None:
        env = {}
    opt_dest = (parser.option_list[-1].dest).upper()
    env[ENV_PREFIX + "_%s" % opt_dest] = parser.option_list[-1]


def add_parser_options(parser, env=None):
    if env is None:
        env = {}
    parser.add_option(
        "--lang",
        action="store",
        default=constants.DEFAULT_LANGUAGE,
        help="""Language code of the translation file. Default: %default""",
    )
    add_env_option(parser, env)
    parser.add_option(
        "--dir",
        action="store",
        default=constants.DEFAULT_TRANSLATION_DIR,
        help="""Path to translations directory. Default: %default""",
    )
    add_env_option(parser, env)
    parser.add_option(
        "--advanced",
        action="store_true",
        default=False,
        help="Flag to enable advanced options",
    )

    group = optparse.OptionGroup(parser, "Logging and debug options")
    group.add_option(
        "--debug",
        default=0,
        action="count",
        help="Add multiple debug flags to increase debug",
    )
    add_env_option(group, env)
    parser.add_option_group(group)

    group = optparse.OptionGroup(parser, "Documentation")
    group.add_option(
        "--changelog",
        action="store_true",
        default=False,
        help="Print out the changelog",
    )
    group.add_option(
        "--license",
        action="store_true",
        default=False,
        help="Print out the software license",
    )
    group.add_option(
        "--readme",
        action="store_true",
        default=False,
        help="Print out README",
    )
    parser.add_option_group(group)


def add_parser_options_advanced(parser, env=None, hide_options=False):
    if env is None:
        env = {}
    group = optparse.OptionGroup(parser, "ADVANCED options")
    if hide_options:
        for op in group.option_list:
            op.help = optparse.SUPPRESS_HELP
    group.add_option(
        "--reverse",
        action="store_true",
        default=False,
        help="""When set, turn strings/values in a file into their keys""",
    )
    add_env_option(parser, env)
    parser.add_option_group(group)


def parse(argv, prog_ver, prog_date):
    # Create our command line parser. We use the older optparse library for compatibility on OneFS
    env_parser = {}
    optparse.OptionParser.format_epilog = lambda self, formatter: self.epilog
    parser = optparse.OptionParser(
        usage=USAGE,
        version="%prog v" + prog_ver + " (" + prog_date + ")",
        epilog=EPILOG,
    )
    add_parser_options(parser, env_parser)
    add_parser_options_advanced(parser, env_parser, ("--advanced" not in argv))
    (raw_options, args) = parser.parse_args(argv[1:])
    print_docs(raw_options.__dict__)
    env_cli_array = []
    for key in env_parser.keys():
        env_value = os.environ.get(key)
        if env_value:
            env_cli_array.append(env_parser[key].get_opt_string())
            env_cli_array.append(env_value)
            setattr(raw_options, env_parser[key].dest, env_parser[key].default)
    if env_cli_array:
        (raw_options, _) = parser.parse_args(env_cli_array, raw_options)
    return (parser, raw_options.__dict__, args)


def print_docs(options, terminate=True):
    documents = []
    zip_handle = None
    for doc_type in [["changelog", "CHANGELOG.md"], ["license", "LICENSE.md"], ["readme", "README.md"]]:
        if options.get(doc_type[0]):
            documents.append(doc_type[1])
    for doc in documents:
        if not zip_handle and zipfile.is_zipfile(sys.argv[0]) or __file__ is None:
            zip_handle = zipfile.ZipFile(sys.argv[0], "r")
        print("%s%s%s" % ("=" * 20, doc, "=" * 20))
        try:
            if zip_handle:
                with zip_handle.open(doc, "r") as f:
                    print(f.read().decode("utf-8"))
            else:
                with open(doc, "r") as f:
                    print(f.read())
        except:
            # If we cannot print out the document, just silently ignore the error
            pass
    if zip_handle:
        zip_handle.close()
    if terminate and documents:
        sys.exit(0)
