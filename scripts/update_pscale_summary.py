#!/usr/bin/env python
# -*- coding: utf8 -*-
"""
update_pscale_summary.py - Create summary statistics for MetadataIQ
"""
# fmt: off
__title__      = "update_pscale_summary"
__version__    = "1.0.0"
__date__       = "23 September 2026"
__license__    = "MIT"
__author__     = "Andrew Chung <andrew.chung@dell.com>"
__maintainer__ = "Andrew Chung <andrew.chung@dell.com>"
__email__      = "andrew.chung@dell.com"
# fmt: on
import argparse
import datetime
import json
import logging
import os
import pathlib
import sys
try:
  from elasticsearch8 import Elasticsearch
  from elasticsearch8 import helpers
  from elasticsearch8 import exceptions as es_exceptions
except:
  try:
    from elasticsearch import Elasticsearch
    from elasticsearch import helpers
    from elasticsearch import exceptions as es_exceptions
  except:
    sys.stderr.write("Could not import the elasticsearch or elasticsearch8 Python library.\n")
    sys.stderr.write("Install elasticsearch for ES 9.x and 10.x\n")
    sys.stderr.write("pip install elasticsearch\n")
    sys.stderr.write("Install elasticsearch8 for ES 8.x and ES 9.x\n")
    sys.stderr.write("pip install elasticsearch8\n")
    sys.exit(99)


DEFAULT_IGNORE_FLAGS = ["ads"]
DEFAULT_LOG_FORMAT = '%(asctime)s - %(module)s|%(funcName)s - %(levelname)s [%(lineno)d] %(message)s'
DEFAULT_MAX_QUERY_SIZE = 10000
DEFAULT_TEMPLATE_INDEX_PATTERN = "isi-metadataiq-summary*"
DEFAULT_TEMPLATE_NAME = "powerscale_summary"
ES_TIMESTAMP_USEC = 1000
TEXT_PROGRAM_DESCRIPTION = """\
NAME
    update_pscale_summary.py - Create summary statistics for MetadataIQ

SYNOPSIS
    update_pscale_summary.py [options]

DESCRIPTION
    The MetadataIQ feature for PowerScale updates a database with the current
    state of the file system. Every update will delete old entries, add new
    entries, and modify entries. There is no history built into the feature
    which limits some forms of capacity reporting. This script aims to provide
    some history for the total cluster capacity as well as provide directory
    summaries for a given set of directories. Through these summaries, it will
    be possible to perform historical capacity usage at the cluster and
    directory level.

USAGE
    The recommended usage of this script is to run this script regularly and
    to run it based on the granularity of the summary data that is desired.
    This schedule should be no shorter than the schedule configured for
    MetadataIQ. If the MetadataIQ update schedule is 1 time per day, then
    running the summary script more than 1 time per day will not produce any
    useful information. Any schedule longer than the MetadataIQ update schedule
    can be used, such as performing the summary 1 time per week or 2 times per
    week while MetadataIQ itself updates 1 time per day. Keeping the same
    target index for multiple clusters is fine as the source cluster name is
    part of each entry so cluster based filters can be used.
    
    The script has several defaults that can be suitable for most environments
    but there are some required parameters to allow the script to function. The
    2 required parameters is the URL to reach ElasticSearch and an API key. The
    API key need to have enough permissions to allows the script to
    create/delete indices, create/delete documents, and create/update an index
    template. The default source index uses a wildcard which will perform the
    summary function over all MetadataIQ indices present on the ElasticSearch
    instance. The default target index name is isi-metadataiq-summary and this
    can be left alone as multiple clusters can use a single target index.
    
    An operation argument should be added in order to perform any actual work.
    The available operations include:
      -cs, --cluster-summary: generate a cluster summary
      -ds, --dir-summary: generate directory
    If no operation arguments are selected, the script can still reset the
    target index as well as perform other operations.
    
    One operation that should be done at least one time is to create the index
    mapping template. This can be done with the --set-template option. An
    example of how to do this is in the examples section.
    
    When selecitng cluster-summary, no additional parameters are required. This
    operation automatically creates summary data consisting of:
      - alternative data stream counts (counted in file counts)
      - directory counts
      - file counts
      - smartlinked file counts (counted in file counts)
      - symbolic link counts (counted in file counts)
      - CloudPool logical capacity used (in bytes)
      - logical capacity used (in bytes)
      - physical capacity used (with all overhead, in bytes)
    In addition, each nodepool will also get the same statistics as the cluster
    summary.
    
    When selecting dir-summary, one or more file names are required. The script
    reads each line in the provided files and interprets each line as a path.
    If a directory name is appended with '/*' as a wildcard, the script will
    skip the parent directory and instead add all subdirectories to process.
    As an example a file could contain the following two lines:
      /ifs/home/*
      /ifs/project/project1
    These 2 lines in the file will cause the script to create summaries for any
    subdirectory of /ifs/home and also the directory /ifs/project/project1.
    
    An index mapping template should be in place before ingesting data into
    ElasticSearch. This can be accomplished with the --set-template option.
    
    If a full reset of the summary index is desired use the --reset-target
    option.

USAGE EXAMPLES
    Create the index template the first time without indexing any data
    python update_pscale_summary.py -u @es_url.txt -k @es_key.txt --set-template

    Basic run with just cluster summary. The ElasticSearch URL and API key are
    supplied by reading them from the files es_url.txt and es_key.txt.
    python update_pscale_summary.py -u @es_url.txt -k @es_key.txt --cs
    
    Example doing both a cluster and directory summary
    python update_pscale_summary.py -u @es_url.txt -k @es_key.txt -cs -ds dir_list.txt
    
    Example where certificate errors are ignored
    python update_pscale_summary.py --insecure -u @es_url.txt -k @es_key.txt -cs -ds dir_list.txt

QUERYING SUMMARY DATA
    In order to make use of the summary data, the schema for the data needs to
    be known. Retrieving data can be done through Elastic queries or Kibana
    visualizations. Below is an abbreviated Python dictionary describing the
    fields that are stored in the index.
    
    {
      "metadata": {
        "cluster_name": <string: cluster_name>
      },
      "summary": {
        "ads": <int: count of alternative data stream files, counted in "files">
        "cloudpool": {
          "logical_size": <int: number of bytes of all CloudPool files>,
          "objects": <int: count of files/directories
        },
        "dirs": <int: count of directories>,
        "files": <int: count of files>,
        "logical_size": <int: logical bytes consumed based on "type" and cluster>,
        "nodepool": <string: name of nodepool or ALL for cluster summary>,
        "objects": <int: count of all files/directories>,
        "physical_size": <int: physical bytes consumed>,
        "smartlinks": <int: number of files tiered through CloudPools>,
        "symlinks": <int: number of files that are symbolic links>
      },
      "timestamp": <time:date the data was queried from the source index>,
      "type": <keyword: possible values: cluster_summary|dir_summary>
    }

ENVIRONMENT VARIABLES
    ELASTIC_URL
        If set, the string will be used as the URL to the ElasticSearch
        instance. This string should include the protocol (http/https)
        and the port number in the standard protocol://fqdn:port format

    ELASTIC_API_KEY
        If set, this is the API key string used to authenticate with
        ElasticSearch

    ELASTIC_SOURCE
        This string will be used as the source index name used in the
        data query to get the summary data
        
    ELASTIC_TARGET
        This is the name of the target index name to write the summary data

DEPENDENCIES
    This script uses the official ElasticSearch Python libraries. The library
    required will depend on the version of ElasticSearch the script needs to
    interact with.
      - Install elasticsearch8 for ES 8.x and ES 9.x
      - Install elasticsearch for versions of Elastic >= 9.x

AUTHOR
    Andrew Chung <andrew.chung@dell.com>

EXIT STATUS
    0   No error
    1   Argument error
    2   Unable to get a list of cluster index names
    3   Unable to create or delete target index
    4   Unable to set index template
    99  Missing Python library\
"""
LOG = logging.getLogger(__name__)


def create_index(es_client, target_index):
  resp = None
  try:
    resp = es_client.indices.create(index=target_index)
  except es_exceptions.NotFoundError:
    return None
  return resp


def delete_index(es_client, target_index):
  resp = None
  try:
    resp = es_client.indices.delete(index=target_index)
  except es_exceptions.NotFoundError:
    return None
  return resp


def get_cluster_list(es_client, source_index):
  resp = None
  try:
    resp = es_client.indices.get(index=source_index)
  except es_exceptions.NotFoundError:
    return None
  return list(resp.keys())


def get_cluster_summary(es_client, es_index):
  cluster_summary_agg_query = {
    "counts": {
      "filters": {
        "filters": {
          "ads": {"term": {"data.user_flags": "ads"}},
          "dirs": {"term": {"data.file_type": "directory"}},
          "files": {"term": {"data.file_type": "regular"}},
          "smartlinks": {"term": {"data.user_flags": "ssmartlinked"}},
          "symlinks": {"term": {"data.file_type": "symlink"}},
        },
      },
    },
    "cloudpool": {
      "filter": {"term": {"data.user_flags": "ssmartlinked"}},
      "aggs": {
        "logical_size": {
          "sum": {"field": "data.size"},
        },
      },
    },
    "logical_size": {
      "sum": {"field": "data.size"},
    },
    "physical_size": {
      "sum": {"field": "data.physical_size"},
    },
    "nodepool": {
      "terms": {"field": "data.data_nodepool.name"},
      "aggs": {
        "counts": {
          "filters": {
            "filters": {
              "ads": {"term": {"data.user_flags": "ads"}},
              "dirs": {"term": {"data.file_type": "directory"}},
              "files": {"term": {"data.file_type": "regular"}},
              "smartlinks": {"term": {"data.user_flags": "ssmartlinked"}},
              "symlinks": {"term": {"data.file_type": "symlink"}},
            },
          },
        },
        "cloudpool": {
          "filter": {"term": {"data.user_flags": "ssmartlinked"}},
          "aggs": {
            "logical_size": {
              "sum": {"field": "data.size"},
            },
          },
        },
        "logical_size": {
          "sum": {"field": "data.size"},
        },
        "physical_size": {
          "sum": {"field": "data.physical_size"},
        },
      },
    },
  }
  resp = es_client.search(
    _source=True,
    aggs=cluster_summary_agg_query,
    fields=["metadata.cluster_name"],
    index=es_index,
    query={"exists": {"field": "metadata.cluster_name"}},
    script_fields={"timestamp": {"script": "new Date().getTime()"}},
    size=1,
  )
  if not resp or not resp["hits"]["hits"]:
    LOG.error("Unable to get cluster summary")
    # Early return if we cannot retrieve a cluster summary
    return None
  agg_base = resp["aggregations"]
  agg_counts = agg_base["counts"]["buckets"]
  results = [
    {
      "metadata": {
        "cluster_name": resp["hits"]["hits"][0]["fields"]["metadata.cluster_name"][0],
      },
      "summary": {
        "ads": agg_counts["ads"]["doc_count"],
        "cloudpool": {
          "logical_size": agg_base["cloudpool"]["logical_size"]["value"],
          "objects": agg_base["cloudpool"]["doc_count"],
        },
        "dirs": agg_counts["dirs"]["doc_count"],
        "files": agg_counts["files"]["doc_count"],
        "logical_size": agg_base["logical_size"]["value"],
        "nodepool": "ALL",
        "objects": agg_counts["dirs"]["doc_count"],
        "physical_size": agg_base["physical_size"]["value"],
        "smartlinks": agg_counts["smartlinks"]["doc_count"],
        "symlinks": agg_counts["symlinks"]["doc_count"],
      },
      "type": "cluster_summary",
      "timestamp": resp["hits"]["hits"][0]["fields"]["timestamp"][0],
    }
  ]
  np_buckets = resp["aggregations"]["nodepool"]["buckets"]
  for np in np_buckets:
    results.append(
      {
        "metadata": {
          "cluster_name": resp["hits"]["hits"][0]["fields"]["metadata.cluster_name"][0],
        },
        "summary": {
          "ads": np["counts"]["buckets"]["ads"]["doc_count"],
          "cloudpool": {
            "logical_size": np["cloudpool"]["logical_size"]["value"],
            "objects": np["cloudpool"]["doc_count"],
          },
          "dirs": np["counts"]["buckets"]["dirs"]["doc_count"],
          "files": np["counts"]["buckets"]["files"]["doc_count"],
          "logical_size": np["logical_size"]["value"],
          "nodepool": np["key"],
          "objects": np["doc_count"],
          "physical_size": np["physical_size"]["value"],
          "smartlinks": np["counts"]["buckets"]["smartlinks"]["doc_count"],
          "symlinks": np["counts"]["buckets"]["symlinks"]["doc_count"],
        },
        "type": "cluster_summary",
        "timestamp": resp["hits"]["hits"][0]["fields"]["timestamp"][0],
      }
    )
  return results


def get_directory_summary(es_client, es_index, dir_paths, ignore_flags=DEFAULT_IGNORE_FLAGS):
  full_dir_list = []
  for dir_path in dir_paths:
    p = pathlib.PurePath(dir_path)
    if p.name == '*':
      path_name = str(p.parent)
      depth = len(p.parent.parts)
    else:
      path_name = str(p)
      depth = len(p.parts) - 1
    full_dir_list.append(
      {
        "bool": {
          "must": [
            {"match_phrase": {"data.path": path_name}},
            {"term": {"data.depth": depth}}
          ],
        },
      }
    )
  sub_dir_name_query = {
      "bool": {
        "must": [
          {
            "bool": {
              "should": full_dir_list
            }
          },
          {
            "term": {"data.file_type": "directory"}
          },
        ],
      },
    }
  LOG.debug("Directory summary query: %s"%json.dumps(sub_dir_name_query, indent=2))
  resp = es_client.search(
    _source=False,
    fields=["data.lin", "data.path"],
    index=es_index,
    query=sub_dir_name_query,
    size=DEFAULT_MAX_QUERY_SIZE,
  )
  LOG.debug(json.dumps(dict(resp), indent=2))
  if not resp or not resp["hits"]["hits"]:
    LOG.error("Query to get directory names returned no results: %s"%str(resp))
    # Early return if no directories are returned
    return None

  sub_paths = [x["fields"]["data.path"][0] for x in resp["hits"]["hits"]]
  agg_filters = {"%s/"%remove_prefix(x, "/ifs"): {"match_phrase_prefix": {"data.file.path": "%s/"%x}} for x in sub_paths}
  match_paths = [{"match_phrase_prefix": {"data.file.path": "%s/"%x}} for x in sub_paths]
  sub_dir_size_query = {
    "bool": {
      "should": match_paths,
    },
  }
  if ignore_flags:
    sub_dir_size_query["bool"]["must_not"] = {"terms": {"data.user_flags": ignore_flags}}
  agg_query = {
    "paths": {
      "filters": {
        "filters": agg_filters,
      },
      "aggs": {
        "ads": {"filter": {"term": {"data.user_flags": "ads"}}},
        "cloudpool": {
          "filter": {"term": {"data.user_flags": "ssmartlinked"}},
          "aggs": {
            "logical_size": {
              "sum": {"field": "data.size"},
            },
          },
        },
        "dirs": {"filter": {"term": {"data.file_type": "directory"}}},
        "files": {"filter": {"term": {"data.file_type": "regular"}}},
        "logical_size": {"sum": {"field": "data.size"}},
        "physical_size": {"sum": {"field": "data.physical_size"}},
        "smartlinks": {"filter": {"term": {"data.user_flags": "ssmartlinked"}}},
        "symlinks": {"filter": {"term": {"data.file_type": "symlink"}}},
      },
    },
  }
  resp = es_client.search(
    _source=False,
    aggs=agg_query,
    fields=["metadata.cluster_name"],
    index=es_index,
    query=sub_dir_size_query,
    script_fields={"timestamp": {"script": "new Date().getTime()"}},
    size=1,
  )
  LOG.debug(json.dumps(dict(resp), indent=2))
  if not resp or not resp["hits"]["hits"]:
    LOG.error("Directory summary query returned no results: %s"%str(resp))
    # Early return if we cannot retrieve any directory summaries
    return None

  buckets = resp["aggregations"]["paths"]["buckets"]
  hits = resp["hits"]["hits"][0]["fields"]
  cluster = hits["metadata.cluster_name"][0]
  timestamp = hits["timestamp"][0]
  # Format the returned results into something easier to parse
  results = [
    {
      "metadata": {
        "cluster_name": cluster,
      },
      "summary": {
        "ads": buckets[x]["ads"]["doc_count"],
        "cloudpool": {
          "logical_size": buckets[x]["cloudpool"]["logical_size"]["value"],
          "objects": buckets[x]["cloudpool"]["doc_count"],
        },
        "dirs": buckets[x]["dirs"]["doc_count"],
        "files": buckets[x]["files"]["doc_count"],
        "logical_size": buckets[x]["logical_size"]["value"],
        "objects": buckets[x]["doc_count"],
        "path": x,
        "physical_size": buckets[x]["physical_size"]["value"],
        "smartlinks": buckets[x]["smartlinks"]["doc_count"],
        "symlinks": buckets[x]["symlinks"]["doc_count"],
      },
      "timestamp": timestamp,
      "type": "dir_summary",
    } 
    for x in buckets.keys()
  ]
  return results


def remove_prefix(text, prefix):
  if text.startswith(prefix):
    return text[len(prefix):]
  return text


def set_summary_template(es_client, name=DEFAULT_TEMPLATE_NAME, pattern=DEFAULT_TEMPLATE_INDEX_PATTERN):
  index_template = {
    "index_patterns": [
      pattern,
    ],
    "template": {
      "settings": {
        "index": {
          "analysis": {
            "analyzer": {
              "path_analyzer": {
                "tokenizer": "path_hierarchy",
              },
            },
          },
          "mode": "standard",
          "routing": {
            "allocation": {
              "include": {
                "_tier_preference": "data_content"
              },
            },
          },
        },
      },
      "mappings": {
        "dynamic": True,
        "subobjects": True,
        "dynamic_date_formats": [
          "strict_date_optional_time",
          "yyyy/MM/dd HH:mm:ss Z||yyyy/MM/dd Z"
        ],
        "dynamic_templates": [],
        "date_detection": True,
        "numeric_detection": True,
        "properties": {
          "metadata.cluster_name": {"type": "keyword"},
          "summary.ads": {"type": "long"},
          "summary.cloudpool.logical_size": {"type": "long"},
          "summary.cloudpool.objects": {"type": "long"},
          "summary.dirs": {"type": "long"},
          "summary.files": {"type": "long"},
          "summary.logical_size": {"type": "long"},
          "summary.objects": {"type": "long"},
          "summary.path": {
            "type": "text",
            "fields": {
              "raw": {
                "type": "keyword"
              }
            },
            "analyzer": "path_analyzer"
          },
          "summary.physical_size": {"type": "long"},
          "summary.smartlinks": {"type": "long"},
          "summary.symlinks": {"type": "long"},
          "timestamp": {"type": "date"},
          "type": {"type": "keyword"},
        },
      },
    },
  }
  resp = es_client.indices.put_index_template(
    body=index_template,
    name=name,
  )
  LOG.debug(json.dumps(dict(resp), indent=2))
  return(resp)


"""
Method to help generate some basic test data by altering the timestamp and logical_size fields
"""
def inject_test_data(es_client, target_index, data, days_offset=30, months_offset=12, simulate=False):
  import copy
  import random

  # Pick the first returned query_time
  parsed_time = datetime.datetime.fromtimestamp(data[0]["timestamp"]/ES_TIMESTAMP_USEC)
  LOG.debug("Parsed time: %s"%parsed_time)
  # Test back dating values
  for i in range(months_offset, 0, -1):
    historical = copy.deepcopy(data)
    new_time = (parsed_time - datetime.timedelta(days=days_offset*i)).timestamp()*ES_TIMESTAMP_USEC
    for entry in historical:
      entry["timestamp"] = int(new_time)
      entry["summary"]["logical_size"] = (entry["summary"]["logical_size"]*(1 - ((i*.8)/months_offset))*random.uniform(0.75,3))
      entry["summary"]["physical_size"] = (entry["summary"]["physical_size"]*(1 - ((i*.8)/months_offset))*random.uniform(0.75,3))
    LOG.debug("Test data: %s"%json.dumps(historical, indent=2))
    if not simulate:
      resp = helpers.bulk(es_client, historical, index=target_index)
      LOG.debug("Bulk index result: %s"%str(resp))


def main():
  parser = argparse.ArgumentParser(
    prog="update_cluster_summary",
    formatter_class=argparse.RawTextHelpFormatter,
    description=TEXT_PROGRAM_DESCRIPTION,
    epilog="",
  )
  parser.add_argument("--insecure",
    action="store_true",
    help="""\
When enabled, disable certificate warnings
(Default: Not set)\
""",
  )
  parser.add_argument("-v", "--verbose",
    action="count",
    default=0,
    help="""\
Make script output verbose
(Default: Not set)\
""",
  )
  parser.add_argument("-cs", "--cluster-summary",
    action="store_true",
    help="""\
Action: gather and update the cluster capacity summary
(Default: Not set)\
""",
  )
  parser.add_argument("-ds", "--dir-summary",
    default=None,
    help="""\
Action: gather and update directory usage summaries. One 
or more filenames are expected after this parameter
Each line in the file should be in the form:
/ifs/some/directory/path
To add all the children of a directory append /* to the
directory name:
/ifs/include/all/children/*
(Default: Not set)\
""",
  )
  parser.add_argument("-u", "--url",
    default=os.getenv("ELASTIC_URL"),
    help="""\
ElasticSearch URL with protocol, host, and port
Can be provided through the environment variable: ELASTIC_URL
If the string is of the form @file where "file" is a file name, the
the URL will be read from the file
This argument is required
(Default: Not set)\
""",
  )
  parser.add_argument("-k", "--key",
    default=os.getenv("ELASTIC_API_KEY"),
    help="""\
ElasticSearch API key string
Can be provided through the environment variable: ELASTIC_API_KEY
If the string is of the form @file where "file" is a file name, the
the key will be read from the file
This argument is required
(Default: Not set)\
""",
  )
  parser.add_argument("-s", "--source",
    default=os.getenv("ELASTIC_SOURCE") or "isi-metadataiq-index.*",
    help="""\
Name of the source ElasticSearch index. Wildcards allowed and each
detected MetadataIQ index will be processed individually
Can be provided through the environment variable: ELASTIC_SOURCE
(Default: isi-metadataiq-index.*)\
""",
  )
  parser.add_argument("-t", "--target",
    default=os.getenv("ELASTIC_TARGET") or "isi-metadataiq-summary",
    help="""\
Name of the target ElasticSearch index
Can be provided through the environment variable: ELASTIC_TARGET
A single index can be used for multiple clusters as all docuemnts
have the cluster name as a field
(Default: isi-metadataiq-summary)\
""",
  )
  parser.add_argument("--ignore",
    nargs="*",
    default=["ads"],
    help="""\
Ignore files with the given OneFS flags. Each flag should follow
the argument with a space. e.g.:
--ignore ads ssmartlinked
By default files with the "ads" attribute are ignored. To include
all flags, use the --ignore argument with no values
(Default: "ads")\
""",
  )
  parser.add_argument("--reset-target",
    action="store_true",
    help="""\
Before indexing new documents into the target index perform an
index delete, index create, and template set
(Default: Not set)\
""",
  )
  parser.add_argument("--set-template",
    action="store_true",
    help="""\
Create or update the index template for cluster and directory
summaries
(Default: Not set)\
""",
  )
  parser.add_argument("--simulate",
    action="store_true",
    help="""\
Perform queries but do not perform any index writes
(Default: Not set)\
""",
  )
  parser.add_argument("--gen-test-data",
    action="store_true",
    help="""\
When this option is selected the script will take a single data
point for botht he cluster and directory summaries and generate
12 months of back data. The logical capacity is the only field
that is modified randomly adding and subtracting capacity
(Default: Not set)\
""",
  )
  args = parser.parse_args()
  if args.verbose > 1:
    LOG.setLevel(logging.DEBUG)
  else:
    LOG.setLevel(logging.INFO)
  if not (args.url or args.key):
    LOG.error("A URL and API key are required arguments.")
    sys.exit(1)
  if args.key.startswith("@"):
    with open(args.key[1:], "r") as f:
      args.key = f.readline().strip()
  if args.url.startswith("@"):
    with open(args.url[1:], "r") as f:
      args.url = f.readline().strip()
  if args.verbose > 2:
    LOG.debug(args)
  
  ignore_flags = ["ads"]
  client = Elasticsearch(
    api_key=args.key,
    hosts=[args.url],
    verify_certs=not args.insecure,
    ssl_show_warn=not args.insecure,
  )

  source_cluster_list = get_cluster_list(client, args.source)
  if not source_cluster_list:
    LOG.error("Unable to get a list cluster index names")
    sys.exit(2)

  if args.reset_target:
    LOG.info("Resetting target index: %s"%args.target)
    resp = delete_index(client, args.target)
    if not resp:
      LOG.warning("Unable to delete index: '%s'. This may not be an issue"%args.target)
    resp = create_index(client, args.target)
    if not resp:
      LOG.error("Unable to create index: '%s'"%args.target)
      sys.exit(3)
    args.set_template = True
    LOG.info("Target index reset: %s"%args.target)

  if args.set_template:
    LOG.info("Creating/updating the summary template")
    resp = set_summary_template(client, DEFAULT_TEMPLATE_NAME, DEFAULT_TEMPLATE_INDEX_PATTERN)
    if not resp:
      LOG.error("Unable to set index template")
      sys.exit(4)
    LOG.info("Summary template create/update complete")

  for cluster_index in source_cluster_list:
    if args.cluster_summary:
      LOG.info("Gathering cluster summary: %s"%cluster_index)
      results = get_cluster_summary(client, cluster_index)
      LOG.debug(json.dumps(results, indent=2))
      if results:
        if not args.simulate:
          resp = helpers.bulk(client, results, index=args.target)
          LOG.debug("Bulk index result: %s"%str(resp))
        if args.gen_test_data:
          # Create back dated test data of 12 months (30 days * 12)
          inject_test_data(client, args.target, results, 30, 12, args.simulate)
      else:
        LOG.error("Unable to get cluster summary: %s"%cluster_index)
      LOG.info("Cluster summary complete: %s"%cluster_index)
    
    if args.dir_summary:
      LOG.info("Gather directory summary: %s"%cluster_index)
      dir_paths = []
      with open(args.dir_summary, "r") as f:
        dir_paths = [x.strip() for x in f.readlines()]
      LOG.debug("Using the following directory paths: %s"%dir_paths)
      results = get_directory_summary(client, cluster_index, dir_paths, ignore_flags)
      if results:
        if not args.simulate:
          resp = helpers.bulk(client, results, index=args.target)
          LOG.debug("Bulk index result: %s"%str(resp))
        if args.gen_test_data:
          # Create back dated test data of 12 months (30 days * 12)
          inject_test_data(client, args.target, results, 30, 12, args.simulate)
      else:
        LOG.error("Unable to get directory summary: %s"%cluster_index)
      LOG.info("Directory summary complete: %s"%cluster_index)

  sys.exit(0)

# __name__ will be __main__ when run directly from the Python interpreter.
# __file__ will be None if the Python files are combined into a ZIP file and executed there
if __name__ == "__main__" or __file__ == None:
    logging.basicConfig(format=DEFAULT_LOG_FORMAT)
    main()
