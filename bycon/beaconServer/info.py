#!/usr/bin/env python3

from bycon import *

"""podmd

* <https://progenetix.org/beacon/info/>

podmd"""

################################################################################
################################################################################
################################################################################

def main():

    try:
        info()
    except Exception:
        print_text_response(traceback.format_exc(), 302)
    
################################################################################

def info():

    initialize_bycon_service(byc, "info")
    r = BeaconInfoResponse(byc)

    defs = byc.get("beacon_defaults", {})
    b_e_d = defs.get("entity_defaults", {})
    info = b_e_d.get("info", {})
    pgx_info = info.get("content", {})
    beacon_info = object_instance_from_schema_name(byc, "beaconInfoResults", "")
    for k in beacon_info.keys():
        if k in pgx_info:
            beacon_info.update({k:pgx_info[k]})

    response = r.populatedInfoResponse(beacon_info)

    # TODO: All the schemas really only here?
    beacon_schemas = []
    for e_t, e_d in b_e_d.items():
        b_s = e_d.get("beacon_schema", {})
        if e_d.get("is_entry_type", True) is True:
            beacon_schemas.append(b_s)

    response.update( { "returned_schemas": beacon_schemas } )
    print_json_response(response)


################################################################################
################################################################################

if __name__ == '__main__':
    main()
