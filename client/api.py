"""This module defines the API for CRDS clients.   Functions defined 
here make remote service calls to the CRDS server to obtain mapping
or reference files and cache them locally.
"""
import os
import os.path
import base64
import re
import urllib2

import crds.log as log
import crds.utils as utils
import crds.rmap as rmap

# ==============================================================================
from crds.client.proxy import CheckingProxy, ServiceError

__all__ = ["getreferences",
           "get_default_context",
           "cache_references",
           
           "set_crds_server", 
           "get_crds_server",
           
           
           "list_mappings",
           "get_mapping_names",
           "get_mapping_url", 

           "get_reference_names",
           "get_reference_url",
           
           "dump_references",
           "dump_mappings",

           "get_best_references",
           "cache_best_references",
           "cache_best_references_for_dataset",
           
           "get_minimum_header"]

# ==============================================================================

# Server for CRDS services and mappings

URL_SUFFIX = "/json/"
URL = os.environ.get("CRDS_SERVER_URL", 'http://etcbrady.stsci.edu:4997')
S = None

def set_crds_server(url):
    """Configure the CRDS JSON services server to `url`,  
    e.g. 'http://localhost:8000'
    """
    if not re.match("http://(\w+\.?)*\w(:\d+)?$", url):
        raise ValueError("Invalid URL " + repr(url) + 
                         " , don't use trailing /")
    global URL, S
    URL = url + URL_SUFFIX
    S = CheckingProxy(URL, version="1.0")

    
def get_crds_server():
    """Return the base URL for the CRDS JSON RPC server.
    """
    return URL[:-len(URL_SUFFIX)]

set_crds_server(URL)

# =============================================================================
def list_mappings(observatory="hst", glob_pattern=".*"):
    """Return the list of mappings associated with `observatory`
    which match `glob_pattern`.
    """
    return [str(x) for x in S.list_mappings(observatory, glob_pattern)]

def get_mapping_url(pipeline_context, mapping):
    """Returns a URL for the specified pmap, imap, or rmap file.
    """
    return S.get_mapping_url(pipeline_context, mapping)

def is_known_mapping(mapping):
    """Return True iff `mapping` is a known/official CRDS mapping file."""
    try:
        return len(get_mapping_url(mapping, mapping)) > 0
    except ServiceError:
        return False
    
def get_mapping_data(pipeline_context, mapping):
    """Returns the contents of the specified pmap, imap, or rmap file
    as a string.
    """
    return S.get_mapping_data(pipeline_context, mapping)
    
def get_mapping_names(pipeline_context):
    """Get the complete set of pmap, imap, and rmap basenames required
    for the specified pipeline_context.   context can be an observatory, 
    pipeline, or instrument context.
    """
    return [str(x) for x in S.get_mapping_names(pipeline_context)]

def get_reference_url(pipeline_context, reference):
    """Returns a URL for the specified reference file.
    """
    return S.get_reference_url(pipeline_context, reference)
    
def get_reference_data(pipeline_context, reference):
    """Returns the contents of the specified reference file as a string.
    """
    return base64.b64decode(S.get_reference_data(pipeline_context, reference))

def get_reference_names(pipeline_context):
    """Get the complete set of reference file basenames required
    for the specified pipeline_context.
    """
    return [str(x) for x in S.get_reference_names(pipeline_context)]

def get_best_references(pipeline_context, header, reftypes=None):
    """Return the dictionary mapping { reftype : reference_basename ... }
    corresponding to the given `header`.  If reftypes is None,  return
    all types;  otherwise return best refs for the list of specified reftypes.
    """
    return S.get_best_references(pipeline_context, dict(header), reftypes)

def get_default_context(observatory):
    """Return the name of the latest pipeline mapping in use for processing
    files for `observatory`.  
    """
    return S.get_default_context(observatory)

# ==============================================================================

class FileCacher(object):
    """FileCacher is an abstract base class which gets remote files
    with simple names into a local cache.
    """
    def _rpc_get_data(self, pipeline_context, name):
        """Fetch the data for `name` via CRDS service and return it.
        """
        return self._get_data(pipeline_context, name)  # Get via jsonrpc

    def _http_get_data(self, pipeline_context, name):
        """Fetch the data for `name` as a URL and return it.
        """
        url = self._get_url(pipeline_context, name)
        log.verbose("Fetching URL ", repr(url))
        return urllib2.urlopen(url).read()

    def get_local_files(self, pipeline_context, names, ignore_cache=False):
        """Given a list of basename `mapping_names` which are pertinent to the 
        given `pipeline_context`,   cache the mappings locally where they can 
        be used by CRDS.
        """
        if isinstance(names, dict):
            names = names.values()
        localpaths = {}
        for i, name in enumerate(names):
            localpath = self._locate(pipeline_context, name)
            if (not os.path.exists(localpath)) or ignore_cache:
                log.verbose("Cache miss. Fetching[%d]" % i, repr(name), 
                            "to", repr(localpath))
                utils.ensure_dir_exists(localpath)
                contents = self._http_get_data(pipeline_context, name)
                open(localpath,"w+").write(contents)
            else:
                log.verbose("Cache hit.  Skipping[%d]" % i, repr(name), 
                            "at", repr(localpath))
            localpaths[name] = localpath
        return localpaths

    def _locate(self, pipeline_context, name):
        return rmap.locate_file(name)

# ==============================================================================

class MappingCacher(FileCacher):
    _get_data = staticmethod(get_mapping_data)
    _get_url = staticmethod(get_mapping_url)
    
MAPPING_CACHER = MappingCacher()

# ==============================================================================

class ReferenceCacher(FileCacher):
    _get_data = staticmethod(get_reference_data)
    _get_url = staticmethod(get_reference_url)

REFERENCE_CACHER = ReferenceCacher()

# ==============================================================================

def dump_mappings(pipeline_context, ignore_cache=False):
    """Given a `pipeline_context`, determine the closure of CRDS mappings and 
    cache them on the local file system.
    
    Returns:   { mapping_basename :   mapping_local_filepath ... }   
    """
    assert isinstance(ignore_cache, bool)
    mappings = get_mapping_names(pipeline_context)
    return MAPPING_CACHER.get_local_files(
        pipeline_context, mappings, ignore_cache=ignore_cache)
  
def dump_references(pipeline_context, baserefs=None, ignore_cache=False):
    """Given a pipeline `pipeline_context` and list of `baserefs` reference 
    file basenames,  obtain the set of reference files and cache them on the
    local file system.   
    
    Returns:   { ref_basename :   reference_local_filepath ... }
    """
    if baserefs is None:
        baserefs = get_reference_names(pipeline_context)
    baserefs = list(baserefs)
    for refname in baserefs:
        if "NOT FOUND" in refname:
            log.verbose("Skipping " + repr(refname))
            baserefs.remove(refname)
    return REFERENCE_CACHER.get_local_files(
        pipeline_context, baserefs, ignore_cache=ignore_cache)

def cache_references(pipeline_context, bestrefs, ignore_cache=False):
    """Given a pipeline `pipeline_context` and `bestrefs` mapping,  obtain the
    set of reference files and cache them on the local file system.   
    
    Returns:   { reference_keyword :   reference_local_filepath ... }   
    """
    bestrefs = dict(bestrefs)
    for filetype, refname in bestrefs.items():
        if "NOT FOUND" in refname:
            log.verbose("Reference type", repr(filetype), 
                        "NOT FOUND.  Ignoring.")
            del bestrefs[filetype]
    localrefs = REFERENCE_CACHER.get_local_files(pipeline_context, bestrefs, 
                                                 ignore_cache=ignore_cache)
    refs = {}
    for filetype, refname in bestrefs.items():
        refs[str(filetype)] = str(localrefs[refname])
    return refs

def cache_best_references(pipeline_context, header, ignore_cache=False):
    """Given the FITS `header` of a dataset and a `pipeline_context`, determine
    the best set of reference files for processing the dataset,  cache them 
    locally,  and return the mapping  { filekind : local_file_path }.
    """
    best_refs = get_best_references(pipeline_context, header)
    local_paths = cache_references(pipeline_context, best_refs, ignore_cache)
    return local_paths

def cache_best_references_for_dataset(pipeline_context, dataset, 
                                      ignore_cache=False):
    """
    determine the best set of reference files,  cache the references
    locally,  and return the mapping  { filekind : local_file_path }.
    """
    header = get_minimum_header(pipeline_context, dataset, ignore_cache)
    return cache_best_references(pipeline_context, header, ignore_cache)

def get_minimum_header(context, dataset, ignore_cache=False):
    """Given a `dataset` and a `context`,  extract relevant header 
    information from the `dataset`.
    """
    dump_mappings(context, ignore_cache)
    ctx = rmap.get_cached_mapping(context)
    return ctx.get_minimum_header(dataset)

# ============================================================================

def getreferences(parameters, reftypes=None, context=None):
    """This is the top-level get reference call for all of CRDS. 
    
    `parameters` should be a dictionary-like object mapping { str: str } for
    crtical best reference related input parameters.
    
    If `reftypes` is None,  return all possible reference types.
    
    If `context` is None,  use the latest available context.
    """
    for key in parameters:
        assert isinstance(key, str), \
            "Non-string key " + repr(key) + " in parameters."
        try:
            parameters[key]
        except Exception:
            raise ValueError("Can't fetch mapping key " + repr(key) + 
                             " from parameters.")
        assert isinstance(parameters[key], str), \
            "Non-string value " + repr(parameters[key]) + \
            " for key " + repr(key) + " in parameters."
    assert isinstance(reftypes, (list, tuple, type(None))), \
        "reftypes must be a list or tuple of strings, or sub-class of those."
    if reftypes is not None:
        for reftype in reftypes:
            assert isinstance(reftype, str), \
                "each reftype must be a string, .e.g. biasfile or darkfile."
    if context is None:
        try:
            instrument = parameters["INSTRUME"]
        except KeyError:
            raise ValueError("No 'INSTRUME' keyword specified,  "
                             "required to determine context.")
        observatory = utils.instrument_to_observatory(instrument)
        ctx = get_default_context(observatory)
    else:
        assert isinstance(context, str) and context.endswith(".pmap"), \
            "context should specify a pipeline mapping, .e.g. hst_0023.pmap"
        ctx = context
    return get_best_references(ctx, parameters, reftypes)
