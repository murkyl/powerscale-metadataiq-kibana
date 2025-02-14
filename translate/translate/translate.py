#!/usr/bin/env python
# -*- coding: utf8 -*-
"""
Prometheus client to export PowerScale network interface statistics
"""
# fmt: off
__title__         = "translate"
__version__       = "1.0.0"
__date__          = "28 November 2024"
__license__       = "MIT"
__author__        = "Andrew Chung <andrew.chung@dell.com>"
__maintainer__    = "Andrew Chung <andrew.chung@dell.com>"
__email__         = "andrew.chung@dell.com"
# fmt: on
import json
import logging
import os
import re
import signal
import subprocess
import sys
import time
import helpers.options_parser as options_parser

DEFAULT_LOG_FORMAT = "%(asctime)s - %(levelname)s - [%(module)s:%(lineno)d] - %(message)s"
LOG = logging.getLogger()


def setup_logging(options):
    log_handler = logging.StreamHandler()
    log_handler.setFormatter(logging.Formatter(DEFAULT_LOG_FORMAT))
    LOG.addHandler(log_handler)
    if options.get("debug", 0):
        LOG.setLevel(logging.DEBUG)
    else:
        LOG.setLevel(logging.INFO)
    if options.get("debug", 0) < 2:
        # Disable loggers for sub modules
        pass


def signal_handler(signum, frame):
    if signum in [signal.SIGINT, signal.SIGTERM]:
        sys.stdout.write("Terminating script\n")
        sys.exit(100)


def translate_descriptions(data, xlate_dict, xlate_keys=None):
    if not xlate_keys:
        xlate_keys = xlate_dict.keys()
    for key in xlate_keys:
        data = data.replace('"description":"%s"' % key, '"description":"%s"' % xlate_dict[key])
    return data


def translate_keys(data, xlate_dict, options=None):
    description_dict = xlate_dict.get("description", {})
    if options.get("reverse"):
        description_dict = {v: k for k, v in description_dict.items()}
    description_keys = description_dict.keys()
    title_dict = xlate_dict.get("title", {})
    if options.get("reverse"):
        title_dict = {v: k for k, v in title_dict.items()}
    title_keys = title_dict.keys()
    label_dict = xlate_dict.get("label", {})
    if options.get("reverse"):
        label_dict = {v: k for k, v in label_dict.items()}
    label_keys = label_dict.keys()

    translated_data = data
    # Translate a panel's description
    translated_data = translate_descriptions(translated_data, description_dict, description_keys)
    # Translate a panel's title
    translated_data = translate_titles(translated_data, title_dict, title_keys)
    # Translate labels
    translated_data = translate_labels(translated_data, label_dict, label_keys)
    # Translate any embedded panelsJSON
    translated_data = translate_panel_json(translated_data, xlate_dict, options)
    return translated_data


def translate_labels(data, xlate_dict, xlate_keys=None):
    if not xlate_keys:
        xlate_keys = xlate_dict.keys()
    for key in xlate_keys:
        data = data.replace('"label":"%s"' % key, '"label":"%s"' % xlate_dict[key])
    return data


def translate_panel_json(data, xlate_dict, options=None):
    match = re.findall(r"\"panelsJSON\":\".*?(?<!\\)\"", data)
    for panel in match:
        panel_json = json.loads("{%s}" % panel)
        panel_data = panel_json["panelsJSON"]
        panel_json["panelsJSON"] = translate_keys(panel_data, xlate_dict, options)
        # Replace the old panelsJSON with the new translated one
        json_output = json.dumps(panel_json, separators=(",", ":"))
        data = data.replace(panel, json_output[1:-1])
    return data


def translate_titles(data, xlate_dict, xlate_keys=None):
    if not xlate_keys:
        xlate_keys = xlate_dict.keys()
    for key in xlate_keys:
        data = data.replace('"title":"%s"' % key, '"title":"%s"' % xlate_dict[key])
    return data


def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Setup command line parser and parse arguments
    (parser, options, args) = options_parser.parse(sys.argv, __version__, __date__)
    setup_logging(options)

    # Start of application code
    input_file = None
    output_file = None
    strings_dict = {}
    strings_file = None
    try:
        strings_file = open(os.path.join(options["dir"], "strings.%s.json" % options["lang"]), "r")
        strings_dict = json.load(strings_file)
    except FileNotFoundError as fnfe:
        sys.stderr.write("Could not open the translation strings file: strings.%s.json" % options["lang"])
        sys.stderr.write("\n")
        sys.exit(1)
    try:
        if len(args) == 1:
            output_file = sys.stdout
        elif len(args) == 2:
            output_file = open(args[1], "w")
        else:
            parser.print_help()
            sys.stderr.write("\n")
            sys.stderr.write("The script only accepts 1 or 2 parameters for the input file and optional output_file")
            sys.stderr.write("\n")
            sys.exit(1)
    except FileNotFoundError as fnfe:
        sys.stderr.write("Could not open the output file: %s" % args[1])
        sys.stderr.write("\n")
        sys.exit(1)
    try:
        input_file = open(args[0], "r")
    except FileNotFoundError as fnfe:
        sys.stderr.write("Could not open the input file: %s" % args[0])
        sys.stderr.write("\n")
        sys.exit(1)

    for line in input_file:
        try:
            line = translate_keys(line, strings_dict, options)
            # Output translated line to the output
            output_file.write(line)
        except Exception as e:
            sys.stderr.write(str(e))
            sys.stderr.write("\n")
            sys.exit(3)
    # Close the input and output files
    input_file.close()
    output_file.close()


if __name__ == "__main__" or __file__ == None:
    main()
