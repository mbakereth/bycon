import json
from pymongo import MongoClient
from bson.objectid import ObjectId

from cgi_utils import *
from biosample_responses import *
from variant_responses import *

################################################################################

def retrieve_individuals(ds_id, byc):

    ind_s = [ ]

    mongo_client = MongoClient()
    data_db = mongo_client[ ds_id ]
    inds_coll = mongo_client[ ds_id ][ "individuals" ]
    bs_coll = mongo_client[ ds_id ][ "biosamples" ]

    ds_results = byc["dataset_results"][ds_id]

    if not "individuals._id" in ds_results:

        ind_s = retrieve_individuals_from_biosample_ids(data_db, ds_results["biosamples.id"][ "target_values" ])

    return ind_s

################################################################################

def retrieve_individuals_from_biosample_ids(data_db, bs_ids):

    ind_s = [ ]

    for bs_id in bs_ids:

        ind = retrieve_variants_for_biosample_by_biosample_id(data_db, bs_id)

        if ind is not False:

            ind_s.append(ind)

    return ind_s

################################################################################

def retrieve_individual_for_biosample_by_biosample_id(data_db, bs_id):

    bs = data_db["biosamples"].find_one({"id":bs_id})

    try:
        return data_db["individuals"].find_one({"id":bs["individual_id"]})
    except:
        return False

################################################################################

def ds_results_phenopack_individuals(ds_id, ds_results):

    mongo_client = MongoClient()
    data_db = mongo_client[ds_id]

    pxf_s = []

    for p in ds_results["individuals.id"]["target_values"]:
        ind = data_db[ "individuals" ].find_one({"id":p})
        pxf = phenopack_individual(ind, ds_results, data_db)
        pxf_s.append(pxf)

    return pxf_s

################################################################################

def phenopack_individual(ind, ds_results, data_db):

    bio_s = retrieve_biosamples_from_individual_id(data_db, ind["id"])
    # bio_s = data_db["biosamples"].find({"individual_id":ind["id"]})

    pxf = {
        "id": ind["id"],
        "subject": ind,
        "biosamples": list(bio_s),
        "metaData": {}
    }

    return pxf


