import cgi, json, re, sys
from urllib.parse import urlparse, parse_qs, unquote
from os import environ
from humps import camelize, decamelize

################################################################################

def parse_query(byc):
    r_m = environ.get('REQUEST_METHOD', '')
    if "POST" in r_m:
        parse_POST(byc)
    else:
        parse_GET(byc)


################################################################################

def set_debug_state(debug: int = 0) -> bool:
    """
    Function to provide a text response header for debugging purposes, i.e. to 
    print out the error or test parameters to a browser session.
    The common way would be to add either a `/debug=1/` part to a REST path or
    to provide a `...&debug=1` query parameter.
    """

    if test_truthy(debug):
        print('Content-Type: text')
        print()
        return True

    r_uri = environ.get('REQUEST_URI', "___none___")
    if re.match(r'^.*?[?&/]debug=(\w+?)\b.*?$', r_uri):
        d = re.match(r'^.*?[?&/]debug=(\w+?)\b.*?$', r_uri).group(1)
        if test_truthy(d):
            print('Content-Type: text')
            print()
            return True

    return False


################################################################################

def select_this_server(byc: dict) -> str:
    """
    Cloudflare based encryption may lead to "http" based server addresses in the
    URI, but then the browser ... will complain if the handover URLs won't use
    encryption. OTOH for local testing one may need to stick w/ http if no pseudo-
    https scenario had been implemented. Therefore handover addresses etc. will
    always use https _unless_ the request comes from a host listed a test instance.
    """

    s_uri = str(environ.get('SCRIPT_URI'))
    local_paths = byc.get("local_paths", {})
    test_sites = local_paths.get("test_domains", [])
    https = "https://"
    http = "http://"

    s = f'{https}{environ.get("HTTP_HOST")}'
    # prdbug(byc, f'===> setting server from {s_uri}')

    for site in test_sites:
        if site in s_uri:
            if https in s_uri:
                s = f'{https}{site}'
            else:
                s = f'{http}{site}'

    # TODO: ERROR hack for https/http mix, CORS...
    # ... since cloudflare provides https mapping using this as fallback

    # prdbug(byc, f'... using {s} <===')

    return s


################################################################################

def parse_POST(byc):
    content_len = environ.get('CONTENT_LENGTH', '0')
    content_typ = environ.get('CONTENT_TYPE', '')

    b_defs = byc.get("beacon_defaults", {})
    form = {}

    # TODO: catch error & return for non-json posts
    if "json" in content_typ:
        body = sys.stdin.read(int(content_len))
        jbod = json.loads(body)
        if "debug" in jbod:
            if jbod["debug"] > 0:
                byc.update({"debug_mode": set_debug_state(1)})

        # TODO: this hacks the v2 structure; ideally should use requestParameters schemas
        if "query" in jbod:
            for p, v in jbod["query"].items():
                if p == "requestParameters":
                    for rp, rv in v.items():
                        rp_d = decamelize(rp)
                        if "datasets" in rp:
                            if "datasetIds" in rv:
                                form.update({"dataset_ids": rv["datasetIds"]})
                        elif "g_variant" in rp:
                            for vp, vv in v[rp].items():
                                vp_d = decamelize(vp)
                                form.update({vp_d: vv})
                        else:
                            form.update({rp_d: rv})
                else:
                    p_d = decamelize(p)
                    form.update({p_d: v})

        # TODO: define somewhere else with proper defaults
        form.update({
            "requested_granularity": jbod.get("requestedGranularity", b_defs.get("requested_granularity", "record")),
            "include_resultset_responses": jbod.get("includeResultsetResponses",
                                                    b_defs.get("include_resultset_responses", "HIT")),
            "include_handovers": jbod.get("includeHandovers", b_defs.get("include_handovers", False)),
            "filters": jbod.get("filters", [])
        })

        # transferring pagination where existing to standard form values
        pagination = jbod.get("pagination", {})
        for p_k in ["skip", "limit"]:
            if p_k in pagination:
                if re.match(r'^\d+$', str(pagination[p_k])):
                    form.update({p_k: pagination[p_k]})
        byc.update({
            "form_data": form,
            "query_meta": jbod.get("meta", {})
        })

################################################################################

def parse_GET(byc):
    b_defs = byc.get("beacon_parameters", {})
    v_defs = byc.get("variant_parameters", {})
    l_defs = byc.get("local_parameters", {})

    f_defs = {**b_defs.get("parameters", {}), **v_defs.get("parameters", {}), **l_defs.get("parameters", {})}

    form = {}

    byc.update({"debug_mode": set_debug_state()})
    get = cgi.FieldStorage()

    for p in get:
        p_d = decamelize(p)
        if p_d in f_defs:
            form.update({p_d: refactor_value_from_defined_type(p, get, f_defs[p_d])})
        # TODO still fallback ..
        else:
            v = get.getvalue(p)
            if "undefined" in v:
                continue
            # making sure double entries are forced to single
            if type(v) is list:
                form.update({p_d: v[0]})
            else:
                form.update({p_d: v})

    # TODO: re-evaluate hack of empty filters which avoids dirty errors downstream
    if not "filters" in form:
        form.update({"filters": []})

    # form.update({
    #     "requested_granularity": get.getvalue("requestedGranularity", b_defs.get("requested_granularity", "record")),
    #     "include_resultset_responses": get.getvalue("includeResultsetResponses",
    #                                                 b_defs.get("include_resultset_responses", "HIT")),
    #     "include_handovers": get.getvalue("includeHandovers", b_defs.get("include_handovers", False))
    # })

    if "requested_schema" in form:
        try:
            byc["query_meta"].update({
                "requested_schemas": [{"entity_type": form["requested_schema"]}]
            })
        except:
            pass

    byc.update({"form_data": form})


################################################################################

def rest_path_elements(byc):
    """
    The function deparses a Beacon REST path into its components and assigns
    those to the respective variables. The assumes structure is:

    `__root__/__request-entity__/__entity-id__/__response-entity__/?query...`
        |             |                 |               |
    "beacon"  e.g. "biosamples"  "pgxbs-t4ee3"  e.g. "genomicVariations"
        |             |                 |               |
    required      required          optional        optional
    """

    r_p_r = byc.get("request_path_root", "beacon")

    if not environ.get('REQUEST_URI'):
        return

    url_comps = urlparse(environ.get('REQUEST_URI'))
    url_p = url_comps.path
    p_items = re.split('/', url_p)

    if not r_p_r in p_items:
        return

    for d_k in ["debug=1", "&debug=1", "debug=true"]:
        if d_k in p_items:
            p_items.remove(d_k)

    p_items = list(filter(None, p_items))
    r_i = p_items.index(r_p_r)

    if len(p_items) == r_i + 1:
        byc.update({"request_entity_path_id": "info"})
        return

    for p_k in ["request_entity_path_id", "request_entity_path_id_value", "response_entity_path_id"]:
        r_i += 1
        if r_i >= len(p_items):
            return
        p_v = unquote(p_items[r_i])
        prdbug(byc, f'...path parsing: {p_k}: {p_v}')
        byc.update({p_k: p_v})


################################################################################

def rest_path_value(key=""):
    """
    This function splits the path of the REQUEST_URI and returns the path element
    after a provided key. The typical uise case would be to get the entity or
    executing script, or an {id} value from a REST path e.g.

    * `/beacon/biosamples/?` => "beacon" -> "biosamples"
    * `/services/cytomapper/?` => "services" -> "cytomapper"
    * `/services/intervalFrequencies/NCIT:C3072/` => "intervalFrequencies" -> "NCIT:C3072"

    """

    if not environ.get('REQUEST_URI'):
        return None

    url_comps = urlparse(environ.get('REQUEST_URI'))
    p_items = re.split('/', url_comps.path)
    p_items = [x for x in p_items if len(x) > 1]
    p_items = [x for x in p_items if not "debug=" in x]

    for i, p in enumerate(p_items, 1):
        if len(p_items) > i:
            if unquote(p) in [key, f'{key}.py', unquote(key)]:
                return unquote(p_items[i])
        elif p == key:
            return None

    return None


################################################################################

def refactor_value_from_defined_type(parameter, form_data, definition):
    p_d_t = definition.get("type", "string")

    if "array" in p_d_t:
        values = form_return_listvalue(form_data, parameter)

        p_i_t = definition.get("items", "string")

        if "int" in p_i_t:
            return list(map(int, values))
        elif "number" in p_i_t:
            return list(map(float, values))
        else:
            return list(map(str, values))

    else:
        value = form_data.getvalue(parameter)

        if "int" in p_d_t:
            return int(value)
        elif "number" in p_d_t:
            return float(value)
        elif "bool" in p_d_t:
            return test_truthy(value)
        else:
            return str(value)


################################################################################

def form_return_listvalue(form_data, parameter):
    l_v = []
    if len(form_data) > 0:
        if parameter in form_data:
            v = form_data.getlist(parameter)
            if "null" in v:
                v.remove("null")
            if "undefined" in v:
                v.remove("undefined")
            if len(v) > 0:
                l_v = ','.join(v)
                l_v = l_v.split(',')

    return l_v


################################################################################

def test_truthy(this):
    if str(this).lower() in ["1", "true", "y", "yes"]:
        return True

    return False


################################################################################

def cgi_break_on_errors(byc):
    if not "error_response" in byc:
        return
    e = byc["error_response"].get("error", {"error_code": 200})
    e_c = e.get("error_code", 200)

    if int(e_c) > 200:
        cgi_print_response(byc, byc["error_response"])


################################################################################

def cgi_print_response(byc, status_code):
    r_f = ""
    f_d = {}

    delint_response(byc)

    if "form_data" in byc:
        f_d = byc["form_data"]

    if "responseFormat" in f_d:
        r_f = f_d["responseFormat"]

    # This is a simple "de-jsonify", intended to be used for already
    # pre-formatted list-like items (i.e. lists only containing objects)
    # with simple key-value pairs)
    # TODO: universal text table converter ... partially implemented

    if "text" in byc["output"]:

        r = byc["service_response"].get("response", "ERROR: No response element in error_response")
        if "result_sets" in r:
            r_s = r["result_sets"][0]
            byc.update({"service_response": r_s.get("results", [])})
        else:
            byc.update({"service_response": r})

        if isinstance(byc["service_response"], dict):
            # TODO: Find where this results/response ambiguity comes from
            if "response" in byc["service_response"]:
                resp = byc["service_response"]["response"]
            elif "results" in byc["service_response"]:
                resp = byc["service_response"]["results"]
            else:
                resp = byc["service_response"]
        else:
            resp = byc["service_response"]
        if isinstance(resp, dict):
            resp = json.dumps(camelize(resp), default=str)
        else:
            l_d = []
            for dp in resp:
                v_l = []
                for v in dp.values():
                    # print(v)
                    v_l.append(str(v))
                l_d.append("\t".join(v_l))
            resp = "\n".join(l_d)

        print_text_response(resp, byc["env"], status_code)

    if test_truthy(byc["form_data"].get("only_handovers", False)):
        try:
            if "result_sets" in byc["service_response"]["response"]:
                for rs_i, rs in enumerate(byc["service_response"]["response"]["result_sets"]):
                    byc["service_response"]["response"]["result_sets"][rs_i].update({"results": []})
        except:
            pass

    update_error_code_from_response_summary(byc)
    switch_to_error_response(byc)
    print_json_response(byc["service_response"], byc["env"])


################################################################################

def update_error_code_from_response_summary(byc):
    if not "response_summary" in byc["service_response"]:
        return

    if not "exists" in byc["service_response"]["response_summary"]:
        return


################################################################################

def switch_to_error_response(byc):
    e_c = byc["error_response"]["error"].get("error_code", 200)

    if e_c == 200:
        return

    if "meta" in byc["service_response"]:
        byc["error_response"].update({"meta": byc["service_response"]["meta"]})
    byc["service_response"] = byc["error_response"]


################################################################################

def delint_response(byc):

    b_s_r = byc["service_response"]

    byc.update({"service_response": response_delete_none_values(b_s_r)})

    try:
        b_h_r = b_s_r.get("beacon_handovers", [])
        if len(b_h_r) < 1:
            byc["service_response"].pop("beacon_handovers", None)
        if not "url" in b_h_r[0]:
            byc["service_response"].pop("beacon_handovers", None)
    except:
        pass


################################################################################

def response_delete_none_values(response):
    """Delete None values recursively from all of the dictionaries"""

    for key, value in list(response.items()):
        if isinstance(value, dict):
            response_delete_none_values(value)
        elif value is None:
            del response[key]
        elif isinstance(value, list):
            for v_i in value:
                if isinstance(v_i, dict):
                    response_delete_none_values(v_i)

    return response


################################################################################

def prdbug(byc, this):
    if byc.get("debug_mode", False) is True:
        prjsonnice(this)


################################################################################

def prjsoncam(this):
    prjsonnice(camelize(this))


################################################################################

def prjsonnice(this):
    print(decamelize_words(json.dumps(this, indent=4, sort_keys=True, default=str)) + "\n")


################################################################################

def decamelize_words(j_d):
    # TODO: move words to config
    de_cams = ["gVariants", "gVariant", "sequenceId", "relativeCopyClass", "speciesId", "chromosomeLocation", "genomicLocation"]
    for d in de_cams:
        j_d = re.sub(r"\b{}\b".format(d), decamelize(d), j_d)

    return j_d


################################################################################

def print_json_response(this={}, env="server", status_code=200):
    if not "local" in env:
        print('Content-Type: application/json')
        print('status:' + str(status_code))
        print()

    prjsoncam(this)
    print()
    exit()


################################################################################

def print_text_response(this="", env="server", status_code=200):
    if "server" in env:
        print('Content-Type: text/plain')
        print('status:' + str(status_code))
        print()

    elif "file" in env:
        # this opion can be used to reroute the response to a file
        return this

    print(this)
    print()
    exit()


################################################################################

def print_uri_rewrite_response(uri_base="", uri_stuff=""):
    print("Status: 302")
    print("Location: {}{}".format(uri_base, uri_stuff))
    print()
    exit()
