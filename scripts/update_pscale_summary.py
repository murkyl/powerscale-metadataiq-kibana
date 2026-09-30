#!/usr/bin/env python
# -*- coding: utf8 -*-
"""
update_pscale_summary.py - Create summary statistics for MetadataIQ
"""
# fmt: off
__title__      = "update_pscale_summary"
__version__    = "1.1.0"
__date__       = "30 September 2026"
__license__    = "MIT"
__author__     = "Andrew Chung <andrew.chung@dell.com>"
__maintainer__ = "Andrew Chung <andrew.chung@dell.com>"
__email__      = "andrew.chung@dell.com"
# fmt: on
import argparse
import collections
import datetime
import functools
import json
import logging
import os
import pathlib
import platform
import re
import ssl
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
try:
    import httplib as api
except ImportError:
    import http.client as api
try:
    from urlparse import urlunsplit
    from urlparse import urljoin
    from urllib import urlencode
except ImportError:
    from urllib.parse import urlunsplit
    from urllib.parse import urljoin
    from urllib.parse import urlencode
if "OneFS" in platform.system():
    import isi.rest
try:
    basestring
except:
    basestring = str


API_PAPI = 1
API_RAN = 2
API_SUPPORT = 4
DEFAULT_API_TIMEOUT = 300
DEFAULT_IGNORE_FLAGS = []
DEFAULT_LOG_FORMAT = '%(asctime)s - %(module)s|%(funcName)s - %(levelname)s [%(lineno)d] %(message)s'
DEFAULT_MAX_QUERY_SIZE = 10000
DEFAULT_TEMPLATE_INDEX_PATTERN = "isi-metadataiq-summary*"
DEFAULT_TEMPLATE_NAME = "powerscale_summary"
ES_TIMESTAMP_USEC = 1000
MAX_SESSION_RETRY = 5
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
    python update_pscale_summary.py -cs -ds dir_list.txt -u @es_url.txt -k @es_key.txt
    
    Example where certificate errors are ignored
    python update_pscale_summary.py -cs -ds dir_list.txt -u @es_url.txt -k @es_key.txt --insecure
    
    Example of getting snapshot data from a cluster
    python update_pscale_summary.py -ss -cl cluster.com:8080 -cu api_user -cp api_user_password -u @es_url.txt -k @es_key.txt --insecure

QUERYING DATA
    In order to make use of the summary data, the schema for the data needs to
    be known. Retrieving data can be done through Elastic queries or Kibana
    visualizations. Below is an abbreviated Python dictionary describing the
    fields that are stored in the index.
    
    {
      "metadata": {
        "cluster_name": <string: cluster_name>
      },
      "snapshot": { # Present for each snapshot on the cluster
        "created": <date: Timestamp for when the snapshot was created>
        "expires": <date: Timestamp for when the snapshot expires>
        "has_locks": <boolean: True if the snapshot is locked>
        "id": <int: Snapshot ID number>
        "name": <str: Name of the snapshot>
        "path": <path: Text with raw as a keyword for the file system path>
        "pct_filesystem": <float: Percentage of the file system used by this snapshot>
        "pct_reserve": <float: Percentage of reserve used by this snapshot>
        "schedule": <str: Snapshot schedule as a OneFS isi-schedule format>
        "shadow_bytes": <int: Number of shadow store bytes used by this snapshot>
        "size": <int: Number of bytes used by this snapshot>
        "state" <keyword: One of active|deleting>
      },
      "snapshot_summary": {
        "aliases": <int: Number of snapshot aliases on the cluster>
        "active_snaps": <int: Number of snapshots in the active state>
        "deleting_snaps": <int: Number of snapshots in the deleting state>
        "pct_filesystem": <float: Percentage of the file system used snapshots>
        "pct_reserve": <float: Percentage of reserve used by snapshots>
        "shadow_bytes": <int: Number of shadow store bytes used by snapshots>
        "size": <int: Number of bytes used by snapshots>
        "total_snaps": <int: Total number of snapshots on the system>
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
      "timestamp": <time:date the data was queried from the source>,
      "type": <keyword: possible values: cluster_summary|dir_summary|snapshot_entry|snapshot_summary>
    }

LIMITATIONS
    Currently, the limit for a single directory summary index is 10,000
    directories. You can run the script multiple times with different
    directory lists to increase the total number of directories that are
    monitored.

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
    5   Cluster URL, user name, and/or password incorrect
    99  Missing Python library\
"""
LOG = logging.getLogger(__name__)
TIMEOUT = 10
URL_CLUSTER_IDENTITY = "/cluster/identity"
URL_PAPI_SESSION = "/session/1/session"
URL_PAPI_PLATFORM_PREFIX = "/platform/%s"
URL_RAN_PLATFORM_PREFIX = "/namespace/%s"
URL_SNAPSHOT_SNAPSHOTS = "/snapshot/snapshots"


def simple_cache(maxsize):
  def decorator(func):
    cache = {}
    @functools.wraps(func)
    def wrapper(*args):
      if args not in cache:
        if len(cache) >= maxsize:
          cache.popitem()
        cache[args] = func(*args)
      return cache[args]
    return wrapper
  return decorator


class papi_lite:
    """Initialize the PAPI lite interface

    user: Text string for the user accessing the API. Used only for HTTP connections.
    password: Text string for the user password. Used only for HTTP connections.
    server: Text string for server URL without the https:// prefix. Just provide the FQDN/IP address and port. e.g. a.b.c.d:8080. Used only for HTTP connections.
    ignorecert: Boolean to disable certificate checking. Used only for HTTP connections.
    oncluster: Boolean or set to None. With a boolean value this will force either usage of internal or not. When set to None, the script will prefer internal API versus HTTP.
    """

    def __init__(
        self,
        user=None,
        password=None,
        server=None,
        ignorecert=True,
        oncluster=None,
    ):
        self.user = user
        self.password = password
        self.server = server
        self.ignorecert = ignorecert
        self.oncluster = oncluster
        self.session = None
        self.csrf = None
        self.ctx = None
        if self.oncluster is None:
            self.oncluster = "OneFS" in platform.system()
        self.init_http_context()

    def init_http_context(self):
        if self.oncluster:
            return
        self.ctx = ssl.create_default_context()
        if self.ignorecert:
            self.ctx.check_hostname = False
            self.ctx.verify_mode = ssl.CERT_NONE

    def create_http_session(self):
        """Connects to a OneFS cluster and gets a PAPI session cookie"""
        if self.oncluster:
            # When running on cluster skip HTTP session creation
            return
        # Cleanup any existing HTTP session
        self.delete_http_session()
        headers = {"Content-type": "application/json", "Accept": "application/json"}
        conn = api.HTTPSConnection(self.server, timeout=TIMEOUT, context=self.ctx)
        # Always ask for both platform and namespace access
        data = json.dumps(
            {
                "username": self.user,
                "password": self.password,
                "services": ["platform", "namespace"],
            }
        )
        try:
            conn.request("POST", URL_PAPI_SESSION, data, headers)
        except IOError as ioe:
            if ioe.errno == 61:
                raise Exception(
                    "Could not connect to the server. Check the URL including port number. Port 8080 is default."
                )
            raise
        except Exception:
            raise
        resp = conn.getresponse()
        msg = resp.read()
        LOG.debug("Response status code: %s" % resp.status)
        LOG.debug("Response: %s" % msg)
        LOG.debug("Headers: %s" % resp.getheaders())
        if resp.status != 200 and resp.status != 201:
            try:
                err_msg = json.loads(msg)["message"]
            except:
                err_msg = "Error creating PAPI session"
            raise Exception(err_msg)
        cookies = resp.getheader("set-cookie").split(";")
        LOG.debug("Cookies line: %s" % cookies)
        session = None
        csrf = None
        for item in cookies:
            if "isisessid=" in item:
                m = re.search(r".*(isisessid=[^;\s]*)", item)
                if m:
                    session = m.group(1).strip()
            if "isicsrf=" in item:
                m = re.search(r".*(isicsrf=[^;]*)", item)
                if m:
                    csrf = m.group(1).strip()
        LOG.debug("Session: %s, CSRF: %s" % (session, csrf))
        conn.close()
        self.session, self.csrf = collections.namedtuple("papi_session", ["session_id", "csrf"])(session, csrf)
        if self.csrf:
            self.csrf = self.csrf.split("=")[1]

    def delete_http_session(self):
        """Cleanup any existing HTTP session"""
        if self.session and not self.oncluster:
            # TODO: Add code to disconnect session
            pass
        self.session = None
        self.csrf = None

    def rest_call(
        self,
        url,
        method=None,
        query_args=None,
        headers=None,
        body=None,
        timeout=DEFAULT_API_TIMEOUT,
        api_type=API_PAPI,
        raw=False,
    ):
        """Perform a REST call either using HTTPS or when run on an Isilon cluster,
        use the internal PAPI socket path or internal RAN socket path

        self: Object state
        url: Can be a full URL string with slashes or an array of strings with no slashes
        method: HTTP method. GET, POST, PUT, DELETE, etc. Default: GET
        query_args: Dictionary of key value pairs to be appended to the URL
        headers: Optional dictionary used to override HTTP headers
        body: Data to be put into the request body
        timeout: Number of seconds to wait for command to complete. Only used for the internal REST call
        api_type: Set to API_PAPI for PAPI calls or API_RAN for RAN calls.

        When using the RAN API, the URL must not include the '/namespace' prefix. The root URL would be: '/ifs'
        """
        resume = True
        response_list = []
        method = method or "GET"
        query_args = query_args or {}
        headers = headers or {}
        body = body or ""
        remote_url = url
        LOG.debug(
            "REST Call params: Method: %s | URL: %s | Query Args: %s" % (method, remote_url, json.dumps(query_args))
        )
        if isinstance(url, basestring):
            remote_url = [str(x) for x in url.split("/") if x]
        if self.oncluster:
            LOG.debug("On cluster query")
            if api_type == API_RAN:
                # The RAN internal call requires a special header to be sent and the "namespace" component to be added to the URL
                headers["SCRIPT_NAME"] = "/namespace"
                remote_url.insert(0, "namespace")
            socket_path = (
                isi.rest.PAPI_SOCKET_PATH * (api_type == API_PAPI)
                or isi.rest.OAPI_SOCKET_PATH * (api_type == API_RAN)
                or isi.rest.RSAPI_SOCKET_PATH * (api_type == API_SUPPORT)
            )
            while resume:
                data = isi.rest.send_rest_request(
                    socket_path=socket_path,
                    method=method,
                    uri=remote_url,
                    query_args=query_args,
                    headers=headers,
                    body=body,
                    timeout=timeout,
                )
                if data:
                    LOG.debug("REST call response: %s" % data[0])
                    try:
                        resume = json.loads(data[2])["resume"]
                        LOG.debug("Resume key: %s" % resume)
                        query_args = {"resume": str(resume) or ""}
                    except:
                        resume = False
                    response_list.append(data)
                else:
                    resume = False
                    LOG.warning("Error occurred getting data from cluster. URL: %s" % remote_url)
        else:
            LOG.debug("HTTPS query")
            conn = None
            max_retry = MAX_SESSION_RETRY
            url_prefix = URL_PAPI_PLATFORM_PREFIX * (api_type == API_PAPI) or URL_RAN_PLATFORM_PREFIX
            try:
                while resume:
                    if not self.session:
                        self.create_http_session()
                    headers["Cookie"] = self.session
                    if self.csrf:
                        headers["X-CSRF-Token"] = self.csrf
                        headers["Referer"] = "https://" + self.server
                    headers["Content-type"] = "application/json"
                    headers["Accept"] = "application/json"
                    LOG.debug("Sending headers: %s" % headers)
                    url = urlunsplit(
                        [
                            "",
                            "",
                            url_prefix % "/".join(remote_url),
                            urlencode(query_args),
                            None,
                        ]
                    )
                    LOG.debug("Method: %s" % method)
                    LOG.debug("URL: %s" % url)
                    LOG.debug("Headers: %s" % headers)
                    # Send request over HTTPS
                    conn = api.HTTPSConnection(self.server, context=self.ctx)
                    conn.request(method, url, body, headers=headers)
                    resp = conn.getresponse()
                    LOG.debug("HTTPS Response code: %d" % resp.status)
                    if resp and 200 <= resp.status < 300:
                        LOG.debug("HTTPS call response: %s" % resp.status)
                        data = resp.read()
                        LOG.debug("Raw data: %s" % data)
                        try:
                            resume_check = json.loads(data)
                        except:
                            resume_check = {}
                        resume = resume_check.get("resume", None)
                        LOG.debug("Resume key: %s" % resume)
                        query_args = {"resume": str(resume) or ""}
                        response_list.append([resp.status, resp.reason, data])
                    elif resp.status == 401:
                        # Our session token has expired so we will re-negotiate a new session
                        self.session = None
                        max_retry -= 1
                        if max_retry:
                            continue
                        raise Exception(
                            "Failed to re-create session token after %d tries. Last try error code: %d"
                            % (MAX_SESSION_RETRY, resp.status)
                        )
                    else:
                        resume = False
                        raise Exception("Error occurred getting data from cluster. Error code: %d" % resp.status)
                if conn:
                    conn.close()
            except IOError as ioe:
                if ioe.errno == 111:
                    raise Exception("Could not connect to server: %s. Check address and port." % self.server)
                else:
                    raise
        try:
            # Combine multiple responses into 1
            response = response_list[0]
            if response[2]:
                json_data = json.loads(response[2])
            else:
                json_data = {}
        except Exception as e:
            if not raw:
                json_data = {}
                response = [500, None]
            else:
                json_data = response_list[0]
                response = [0, None]
        if len(response_list) > 1:
            keys = list(json_data.keys())
            try:
                keys.remove("total")
            except:
                pass
            keys.remove("resume")
            if len(keys) > 1:
                raise Exception("More keys remaining in REST call response than we expected: %s" % keys)
            key = keys[0]
            for i in range(1, len(response_list)):
                json_data[key] = json_data[key] + json.loads(response_list[i][2])[key]
        return response[0], response[1], json_data


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


@simple_cache(1024)
def get_cluster_name(papi_client):
  resp = papi_client.rest_call(
      URL_CLUSTER_IDENTITY,
      "GET",
      query_args={},
  )
  if resp[0] != 200:
    LOG.error("Error in PAPI request to {url}:\n{err}".format(err=str(data), url=URL_CLUSTER_IDENTITY))
    return None
  return resp[2]["name"]


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
            {"match_phrase_prefix": {"data.path": path_name}},
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
  match_paths = [{"match_phrase_prefix": {"data.path": "%s/"%x}} for x in sub_paths]
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


def get_snapshot_summary(papi_client):
  cluster_name = get_cluster_name(papi_client)
  resp = papi_client.rest_call(
      URL_SNAPSHOT_SNAPSHOTS,
      "GET",
      query_args={"state": "all"},
  )
  if resp[0] != 200:
    LOG.error("Error in PAPI request to {url}:\n{err}".format(err=str(data), url=URL_SNAPSHOT_SNAPSHOTS))
    return None
  now = datetime.datetime.now(datetime.UTC).timestamp()*ES_TIMESTAMP_USEC
  results = [
    {
      "metadata": {
        "cluster_name": cluster_name,
      },
      "snapshot_summary": {
        "aliases": 0,
        "active_snaps": 0,
        "deleting_snaps": 0,
        "pct_filesystem": 0,
        "pct_reserve": 0,
        "shadow_bytes": 0,
        "size": 0,
        "total_snaps": 0,
      },
      "type": "snapshot_summary",
      "timestamp": now,
    }
  ]
  summary = results[0]["snapshot_summary"]
  for snap in resp[2].get("snapshots"):
    if snap["alias"]:
      summary["aliases"] += 1
      continue
    if snap["state"] == "active":
      summary["active_snaps"] += 1
    else:
      summary["deleting_snaps"] += 1
    for key in ["pct_filesystem", "pct_reserve", "shadow_bytes", "size"]:
      summary[key] += snap[key]
    summary["total_snaps"] += 1
    snap["created"] = snap["created"]*ES_TIMESTAMP_USEC if snap["created"] else None
    snap["expires"] = snap["expires"]*ES_TIMESTAMP_USEC if snap["expires"] else None
    snap.pop("alias", None)
    snap.pop("target_id", None)
    snap.pop("target_name", None)
    results.append({
      "metadata": {
        "cluster_name": cluster_name,
      },
      "snapshot": snap,
      "type": "snapshot_entry",
      "timestamp": now,
    })
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
          "snapshot.alias": {"type": "keyword"},
          "snapshot.created": {"type": "date"},
          "snapshot.expires": {"type": "date"},
          "snapshot.has_locks": {"type": "boolean"},
          "snapshot.id": {"type": "long"},
          "snapshot.name": {"type": "keyword"},
          "snapshot.path": {
            "type": "text",
            "fields": {
              "raw": {
                "type": "keyword"
              },
            },
            "analyzer": "path_analyzer",
          },
          "snapshot.pct_filesystem": {"type": "float"},
          "snapshot.pct_reserve": {"type": "float"},
          "snapshot.schedule": {"type": "keyword"},
          "snapshot.shadow_bytes": {"type": "long"},
          "snapshot.size": {"type": "long"},
          "snapshot.state": {"type": "keyword"},
          "snapshot.target_id": {"type": "long"},
          "snapshot.target_name": {"type": "keyword"},
          "snapshot_summary.aliases": {"type": "long"},
          "snapshot_summary.active_snaps": {"type": "long"},
          "snapshot_summary.deleting_snaps": {"type": "long"},
          "snapshot_summary.pct_filesystem": {"type": "float"},
          "snapshot_summary.pct_reserve": {"type": "float"},
          "snapshot_summary.shadow_bytes": {"type": "long"},
          "snapshot_summary.size": {"type": "long"},
          "snapshot_summary.total_snaps": {"type": "long"},
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
              },
            },
            "analyzer": "path_analyzer",
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
  parser.add_argument("--version",
    action="store_true",
    help="""\
Output script name and version\
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
  parser.add_argument("-ss", "--snap-summary",
    action="store_true",
    help="""\
Action: gather and update snapshot usage summaries. This action
requires the cluster URL, user, and password arguments are specified.
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
  parser.add_argument("-cl", "--cluster-url",
    nargs="*",
    default=os.getenv("CLUSTER_URL"),
    help="""\
PowerScale host and port value. e.g. mycluster.com:8080
If multiple clusters are to be monitored, the file format is required
and each line in the file should be their own host:port pair.
Can be provided through the environment variable: CLUSTER_URL
If the string is of the form @file where "file" is a file name, the
the URL will be read from the file
(Default: Not set)\
""",
  )
  parser.add_argument("-cu", "--cluster-user",
    nargs="*",
    default=os.getenv("CLUSTER_USER"),
    help="""\
PowerScale user with appropriate PAPI permissions.
If multiple clusters are to be monitored, the file format is required
and each line in the file should be the user for cluster in the same
order as the cluster URLs are listed.
Can be provided through the environment variable: CLUSTER_USER
If the string is of the form @file where "file" is a file name, the
the URL will be read from the file
(Default: Not set)\
""",
  )
  parser.add_argument("-cp", "--cluster-password",
    nargs="*",
    default=os.getenv("CLUSTER_PASSWORD"),
    help="""\
Password for the provided cluster user.
If multiple clusters are to be monitored, the file format is required
and each line in the file should be the password for cluster in the
same order as the cluster URLs are listed.
Can be provided through the environment variable: CLUSTER_PASSWORD
If the string is of the form @file where "file" is a file name, the
the URL will be read from the file
(Default: Not set)\
""",
  )
  parser.add_argument("--ignore",
    nargs="*",
    default=DEFAULT_IGNORE_FLAGS,
    help="""\
Ignore files with the given OneFS flags. Each flag should follow
the argument with a space. e.g.:
--ignore ads ssmartlinked
By default all files, including "ads" files are included.
(Default: Not set)\
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
  client = None
  papi = []
  if args.verbose > 1:
    LOG.setLevel(logging.DEBUG)
  else:
    LOG.setLevel(logging.INFO)
  if not (args.url or args.key):
    LOG.error("A URL and API key are required arguments.")
    sys.exit(1)
  for argvar in ["key", "url"]:
    if getattr(args, argvar).startswith("@"):
      with open(getattr(args, argvar)[1:], "r") as f:
        setattr(args, argvar, f.readline().strip())
  for argvar in ["cluster_url", "cluster_user", "cluster_password"]:
    if getattr(args, argvar)[0].startswith("@"):
      with open(getattr(args, argvar)[0][1:], "r") as f:
        setattr(args, argvar, [x.strip() for x in f.readlines()])
  if args.verbose > 2:
    LOG.debug(args)
  if args.version:
    sys.stdout.write("%s %s (%s)\n"%(__title__, __version__, __date__))
    sys.exit(0)
  
  client = Elasticsearch(
    api_key=args.key,
    hosts=[args.url],
    verify_certs=not args.insecure,
    ssl_show_warn=not args.insecure,
  )
  
  if args.cluster_url and args.cluster_user and args.cluster_password:
    if len(set([
      len(args.cluster_url),
      len(args.cluster_user),
      len(args.cluster_password)
      ]
    )) != 1:
      LOG.error("Cluster URL, user name, and password lengths do not match")
      sys.exit(5)

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
      results = get_directory_summary(client, cluster_index, dir_paths, args.ignore)
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

    if args.snap_summary:
      LOG.info("Gather snapshot summary")
      for i in range(len(args.cluster_url)):
        LOG.info("Gathering snapshot data for: %s"%args.cluster_url[i])
        papi.append(papi_lite(
          ignorecert=args.insecure,
          password=args.cluster_password[i],
          server=args.cluster_url[i],
          user=args.cluster_user[i],
        ))
        results = get_snapshot_summary(papi[i])
        if results:
          if not args.simulate:
            resp = helpers.bulk(client, results, index=args.target)
            LOG.debug("Bulk index result: %s"%str(resp))
        else:
          LOG.error("Unable to get cluster snapshot for: %s"%args.cluster_url[i])
      LOG.info("Cluster snapshot summary complete")

  sys.exit(0)

# __name__ will be __main__ when run directly from the Python interpreter.
# __file__ will be None if the Python files are combined into a ZIP file and executed there
if __name__ == "__main__" or __file__ == None:
    logging.basicConfig(format=DEFAULT_LOG_FORMAT)
    main()
