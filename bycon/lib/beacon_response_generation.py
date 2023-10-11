from deepmerge import always_merger
from os import environ

from bycon_plot import ByconPlot
from bycon_helpers import mongo_result_list, mongo_test_mode_query, return_paginated_list
from cgi_parsing import prdbug
from datatable_utils import export_datatable_download
from export_file_generation import *
from file_utils import ByconBundler, callset_guess_probefile_path
from handover_generation import dataset_response_add_handovers
from query_execution import execute_bycon_queries
from query_generation import ByconQuery
from read_specs import datasets_update_latest_stats
from response_remapping import *
from variant_mapping import ByconVariant
from schema_parsing import object_instance_from_schema_name

################################################################################

class BeaconDataResponse:

    def __init__(self, byc: dict):
        self.byc = byc
        self.test_mode = byc.get("test_mode", False)
        self.beacon_defaults = byc.get("beacon_defaults", {})
        self.entity_defaults = self.beacon_defaults.get("entity_defaults", {"info":{}})
        self.form_data = byc.get("form_data", {})
        self.service_config = self.byc.get("service_config", {})
        self.response_schema = byc["response_schema"]
        self.requested_granularity = self.form_data.get("requested_granularity", "record")
        self.beacon_schema = self.byc["response_entity"].get("beacon_schema", "___none___")
        self.data_response = object_instance_from_schema_name(byc, self.response_schema, "")
        self.error_response = object_instance_from_schema_name(byc, "beaconErrorResponse", "")
        self.__meta_add_received_request_summary_parameters()
        self.__meta_add_parameters()
        self.__meta_clean_parameters()

        return
    

    # -------------------------------------------------------------------------#
    # ----------------------------- public ------------------------------------#
    # -------------------------------------------------------------------------#

    def resultsetResponse(self):
        if not "beaconResultsetsResponse" in self.response_schema:
            return

        rss, queries = ByconResultSets(self.byc).populatedResultSets()
        r_m = self.data_response["meta"]
        r_m.update({"info": always_merger.merge(r_m.get("info", {}), {"original_queries": queries})})
        self.data_response["response"].update({"result_sets": rss})
        self.__resultset_response_update_summaries()
        if not "record" in self.requested_granularity:
            self.data_response.pop("response", None)
        if "boolean" in self.requested_granularity:
            self.data_response["response_summary"].pop("num_total_results", None)
        return self.data_response


    # -------------------------------------------------------------------------#

    def collectionsResponse(self):
        if not "beaconCollectionsResponse" in self.response_schema:
            return

        colls = ByconCollections(self.byc).populatedCollections()
        self.data_response["response"].update({"collections": colls})
        self.__collections_response_update_summaries()
        return self.data_response


    # -------------------------------------------------------------------------#

    def filteringTermsResponse(self):
        if not "beaconFilteringTermsResponse" in self.response_schema:
            return

        fts, ress = ByconFilteringTerms(self.byc).populatedFilteringTerms()
        self.data_response["response"].update({"filteringTerms": fts})
        self.data_response["response"].update({"resources": ress})
        # self.__filtering_terms_response_update_summaries()
        return self.data_response


    # -------------------------------------------------------------------------#

    def errorResponse(self):
        return self.error_response


    # -------------------------------------------------------------------------#
    # ----------------------------- private -----------------------------------#
    # -------------------------------------------------------------------------#

    def __meta_clean_parameters(self):
        r_m = self.data_response.get("meta", {})

        if "beaconCollectionsResponse" in self.response_schema:
            r_m.get("received_request_summary", {}).pop("include_resultset_responses", None)


    # -------------------------------------------------------------------------#

    def __meta_add_parameters(self):

        r_m = self.data_response.get("meta", {})

        if "test_mode" in r_m:
            r_m.update({"test_mode":self.test_mode})
        if "returned_schemas" in r_m:
            r_m.update({"returned_schemas":[self.beacon_schema]})

        info = self.entity_defaults["info"].get("content", {"api_version": "___none___"})
        for p in ["api_version", "beacon_id"]:
            if p in info.keys():
                r_m.update({p: info.get(p, "___none___")})

        form = self.form_data
        # TODO: this is hacky; need a separate setting of the returned granularity
        # since the server may decide so...
        if self.requested_granularity and "returned_granularity" in r_m:
            r_m.update({"returned_granularity": form.get("requested_granularity")})

        service_meta = self.service_config.get("meta", {})
        for rrs_k, rrs_v in service_meta.items():
            r_m.update({rrs_k: rrs_v})

        return

    # -------------------------------------------------------------------------#

    def __meta_add_received_request_summary_parameters(self):
        r_m = self.data_response.get("meta", {})
        if not "received_request_summary" in r_m:
            return

        r_r_s = r_m["received_request_summary"]

        r_r_s.update({
            "requested_schemas": [self.beacon_schema]
        })

        for name in ["dataset_ids", "test_mode"]:
            value = self.byc.get(name)
            if not value:
                continue
            r_r_s.update({name: value})

        vargs = self.byc.get("varguments", [])
        # TODO: a bit hacky; len == 1 woulld be the default assemblyId ...
        if len(vargs) > 1:
            r_r_s.update({"request_parameters":{"g_variant":vargs}})

        fs = self.byc.get("filters", [])
        fs_p = []
        if len(fs) > 0:
            for f in fs:
                fs_p.append(f.get("id"))
            r_r_s.update({"filters":fs_p})
        else:
            r_r_s.pop("filters", None)

        form = self.form_data
        for p in ["include_resultset_responses", "requested_granularity"]:
            if p in form and p in r_r_s:
                r_r_s.update({p: form.get(p)})

        for q in ["cohort_ids"]:
            if q in form:
                r_r_s.update({"request_parameters": always_merger.merge( r_r_s.get("request_parameters", {}), { "cohort_ids": form.get(q) })})

        info = self.entity_defaults["info"].get("content", {"api_version": "___none___"})
        for p in ["api_version"]:
            if p in info.keys():
                r_r_s.update({p: info.get(p, "___none___")})

        return


    # -------------------------------------------------------------------------#

    def __resultset_response_update_summaries(self):
        if not "beaconResultsetsResponse" in self.response_schema:
            return
        if not "response" in self.data_response:
            return
        rsr = self.data_response["response"].get("result_sets")
        if not rsr:
            return

        t_count = 0
        t_exists = False
        for i, r_s in enumerate(rsr):
            res = r_s.get("results", [])
            t_count += len(res)

        if t_count > 0:
            t_exists = True

        self.data_response.update({
            "response_summary": {
                "num_total_results": t_count,
                "exists": t_exists
            }
        })

        return


   # -------------------------------------------------------------------------#

    def __collections_response_update_summaries(self):
        if not "beaconCollectionsResponse" in self.response_schema:
            return
        if not "response" in self.data_response:
            return
        c_r = self.data_response["response"].get("collections")
        if not c_r:
            return

        t_count = len(c_r)

        if t_count > 0:
            t_exists = True

        self.data_response.update({
            "response_summary": {
                "num_total_results": t_count,
                "exists": t_exists
            }
        })

        return


################################################################################
################################################################################
################################################################################

class ByconFilteringTerms:

    def __init__(self, byc: dict):
        self.byc = byc
        self.test_mode = byc.get("test_mode", False)
        self.test_mode_count = byc.get("test_mode_count", 5)
        self.dataset_ids = byc.get("dataset_ids", [])
        self.beacon_defaults = byc.get("beacon_defaults", {})
        self.entity_defaults = self.beacon_defaults.get("entity_defaults", {"info":{}})
        self.filter_definitions = byc.get("filter_definitions", {})
        self.form_data = byc.get("form_data", {})
        self.filters = byc.get("filters", [])
        self.output = byc.get("output", "___none___")
        self.response_entity_id = byc.get("response_entity_id", "filteringTerm")
        self.data_collection = byc["response_entity"].get("collection", "collations")
        self.path_id_value = byc.get("request_entity_path_id_value", False)
        self.filter_collation_types = set()
        self.filtering_terms = []
        self.filter_resources = []

        return

    # -------------------------------------------------------------------------#
    # ----------------------------- public ------------------------------------#
    # -------------------------------------------------------------------------#

    def populatedFilteringTerms(self):
        self.__return_filtering_terms()
        self.__return_filter_resources()
        return self.filtering_terms, self.filter_resources

    # -------------------------------------------------------------------------#
    # ----------------------------- private -----------------------------------#
    # -------------------------------------------------------------------------#

    def __return_filtering_terms(self):

        f_coll = self.data_collection

        ft_fs = []
        for f in self.filters:
            ft_fs.append('(' + f.get("id", "___none___") + ')')
        if len(ft_fs) > 0:
            f_s = '|'.join(ft_fs)
            f_re = re.compile(r'^' + '|'.join(ft_fs))
        else:
            f_re = None

        # TODO: This should be derived from some entity definitions
        # TODO: whole query generation in separate function ...
        scopes = ["biosamples", "individuals", "analyses", "genomicVariations"]
        query = {}
        q_list = []

        q_scope = self.form_data.get("scope", "___none___")
        if q_scope in scopes:
            q_list.append({"scope": q_scope})

        q_types = self.form_data.get("collation_types", [])
        if len(q_types) > 0:
            q_list.append({"collation_type": {"$in": q_types }})

        if len(q_list) == 1:
            query = q_list[0]
        elif len(q_list) > 1:
            query = {"$and": q_list}

        if self.test_mode is True:
            query, error = mongo_test_mode_query(self.dataset_ids[0], f_coll, self.test_mode_count)

        for ds_id in self.dataset_ids:
            fields = {"_id": 0}
            f_s, e = mongo_result_list(ds_id, f_coll, query, fields)
            t_f_t_s = []
            for f in f_s:
                self.filter_collation_types.add(f.get("collation_type", None))
                f_t = {"count": f.get("count", 0)}
                for k in ["id", "label"]:
                    if k in f:
                        f_t.update({k: f[k]})
                f_t.update({"type": f.get("ft_type", "ontologyTerm")})
                if "ontologyTerm" in f_t["type"]:
                    f_t.update({"type": f.get("name", "ontologyTerm")})

                # TODO: this is not required & also not as defined (singular `scope`)
                # f_t.update({"scopes": scopes})
                t_f_t_s.append(f_t)
            self.filtering_terms.extend(t_f_t_s)

        return

    # -------------------------------------------------------------------------#

    def __return_filter_resources(self):
        r_o = {}

        f_d_s = self.filter_definitions
        collation_types = list(self.filter_collation_types)
        res_schema = object_instance_from_schema_name(self.byc, "beaconFilteringTermsResults", "definitions/Resource",
                                                      "json")
        for c_t in collation_types:
            f_d = f_d_s[c_t]
            r = {}
            for k in res_schema.keys():
                if k in f_d:
                    r.update({k: f_d[k]})

            r_o.update({f_d["namespace_prefix"]: r})

        for k, v in r_o.items():
            self.filter_resources.append(v)

        return


################################################################################
################################################################################
################################################################################

class ByconCollections:

    def __init__(self, byc: dict):
        self.byc = byc
        self.dataset_ids = byc.get("dataset_ids", [])
        self.test_mode = byc.get("test_mode", False)
        self.test_mode_count = byc.get("test_mode_count", 5)
        self.beacon_defaults = byc.get("beacon_defaults", {})
        self.entity_defaults = self.beacon_defaults.get("entity_defaults", {"info":{}})
        self.filter_definitions = byc.get("filter_definitions", {})
        self.form_data = byc.get("form_data", {})
        self.output = byc.get("output", "___none___")
        self.response_entity_id = byc.get("response_entity_id", "dataset")
        self.data_collection = byc["response_entity"].get("collection", "collations")
        self.path_id_value = byc.get("request_entity_path_id_value", False)
        self.collections = []

        return


    # -------------------------------------------------------------------------#
    # ----------------------------- public ------------------------------------#
    # -------------------------------------------------------------------------#

    def populatedCollections(self):
        self.__collections_return_datasets()
        self.__collections_return_cohorts()
        return self.collections

    # -------------------------------------------------------------------------#
    # ----------------------------- private -----------------------------------#
    # -------------------------------------------------------------------------#

    def __collections_return_datasets(self):
        if not "dataset" in self.response_entity_id:
            return
        dbstats = datasets_update_latest_stats(self.byc)
        for i, d_s in enumerate(dbstats):
            ds_id = d_s.get("id", "___none___")
            if ds_id in self.dataset_ids:
                # TODO: remove verifier hack
                for t in ["createDateTime", "updateDateTime"]:
                    d = str(d_s.get(t, "1967-11-11"))
                    if re.match(r'^\d\d\d\d\-\d\d\-\d\d$', d):
                        dbstats[i].update({t:f'{d}T00:00:00+00:00'})

        self.collections = dbstats

        return


    # -------------------------------------------------------------------------#

    def __collections_return_cohorts(self):
        if not "cohort" in self.response_entity_id:
            return

        # TODO: reshape cohorts according to schema

        cohorts =  []
        query = { "collation_type": "pgxcohort" }
        limit = 0
        c_q = self.form_data.get("cohort_ids", [])

        if len(c_q) > 0:
            query = { "id": {"$in": c_q} }
        elif self.path_id_value is not False:
            query = { "id": self.path_id_value }

        if self.test_mode is True:
            limit = self.test_mode_count

        mongo_client = MongoClient(host=environ.get("BYCON_MONGO_HOST", "localhost"))
        for ds_id in self.dataset_ids:
            mongo_db = mongo_client[ ds_id ]        
            mongo_coll = mongo_db[ "collations" ]
            for cohort in mongo_coll.find( query, limit=limit ):
                cohorts.append(cohort)

        self.collections = cohorts

        return


################################################################################

class ByconResultSets:

    def __init__(self, byc: dict):
        self.byc = byc
        self.beacon_defaults = byc.get("beacon_defaults", {})
        self.entity_defaults = self.beacon_defaults.get("entity_defaults", {"info":{}})
        self.datasets_results = dict()  # the object with matched ids perdataset, per h_o
        self.datasets_data = dict()     # the object with data of requested entity per dataset
        self.result_sets = list()       # data rewrapped into the resultSets list
        self.filter_definitions = byc.get("filter_definitions", {})
        self.form_data = byc.get("form_data", {})
        self.output = byc.get("output", "___none___")
        self.data_collection = byc["response_entity"].get("collection", "biosamples")
        self.response_entity_id = byc.get("response_entity_id", "biosample")

        pagination = byc.get("pagination", {"skip": 0, "limit": 0})
        self.limit = pagination.get("limit", 0)
        self.skip = pagination.get("skip", 0)

        self.record_queries = ByconQuery(byc).recordsQuery()

        self.__create_empty_result_sets()
        self.__get_handover_access_key()
        self.__retrieve_datasets_results()
        # next some methods for non-standard responses (i.e. beyond Beacon ...)
        # first the methods which use data streaming, i.e. do not retrieve the data first
        self.__check_datasets_0_results_pgxseg_export()
        self.__check_datasets_0_results_vcf_export()
        self.__check_result_sets_matrix_export()
        # retrieving the data if not exited above
        self.__retrieve_datasets_data()
        self.__retrieve_variants_data()
        # tables before reshaping ...
        self.__check_datasets_data_table_export()
        self.__check_datasets_results_histoplot_delivery()
        self.__check_datasets_results_samplesplot_delivery()
        self.__check_biosamples_map_delivery()
        # finally populating the standard Beacon response
        self.__populate_result_sets()
        # if still here (i.e. non of the above was successful) now saving
        # this could be separate ...
        self.__result_sets_save_handovers()


    # -------------------------------------------------------------------------#
    # ----------------------------- public ------------------------------------#
    # -------------------------------------------------------------------------#

    def populatedResultSets(self):
        return self.result_sets, self.record_queries

    # -------------------------------------------------------------------------#
    # ----------------------------- private -----------------------------------#
    # -------------------------------------------------------------------------#

    def __get_handover_access_key(self):
        r_c = self.data_collection
        # fallback
        r_k = r_c+"_id"

        for r_t, r_d in self.entity_defaults.items():
            r_t_k = r_d.get("h->o_access_key")
            if not r_t_k:
                continue
            if r_d.get("response_entity_id", "___none___") == self.response_entity_id:
                r_k = r_d.get("h->o_access_key", r_k)

        self.handover_key = r_k

        return


    # -------------------------------------------------------------------------#

    def __check_datasets_data_table_export(self):
        if not "table" in self.output:
            return

        collated_results = []
        for ds_id, data in self.datasets_data.items():
            collated_results += data

        export_datatable_download(collated_results, self.byc)


    # -------------------------------------------------------------------------#
 
    def __check_datasets_0_results_pgxseg_export(self):
        """

        """
        if not "pgxseg" in self.output:
            return

        ds_id = list(self.datasets_results.keys())[0]
        export_pgxseg_download(self.datasets_results, ds_id, self.byc)
        return


    # -------------------------------------------------------------------------#
 
    def __check_datasets_0_results_vcf_export(self):
        """

        """
        if not "vcf" in self.output:
            return

        ds_id = list(self.datasets_results.keys())[0]
        export_vcf_download(self.datasets_results, ds_id, self.byc)

        return


    # -------------------------------------------------------------------------#

    def __check_result_sets_matrix_export(self):
        if not "pgxmatrix" in self.output:
            return

        ds_id = list(self.datasets_results.keys())[0]
        export_callsets_matrix(self.datasets_results, ds_id, self.byc)
        return


    # -------------------------------------------------------------------------#

    def __check_biosamples_map_delivery(self):




        return
    # -------------------------------------------------------------------------#

    def __check_datasets_results_samplesplot_delivery(self):
        if not "samplesplot" in self.output:
            return

        results = []

        for ds_id, ds_res in self.datasets_results.items():
            if not "callsets._id" in ds_res:
                continue

            mongo_client = MongoClient(host=environ.get("BYCON_MONGO_HOST", "localhost"))
            cs_coll = mongo_client[ds_id]["callsets"]
            var_coll = mongo_client[ds_id]["variants"]

            cs_r = ds_res["callsets._id"]
            cs__ids = cs_r["target_values"]
            r_no = len(cs__ids)
            if r_no < 1:
                continue
            cs__ids = return_paginated_list(cs__ids, self.skip, self.limit)

            for cs__id in cs__ids:
                cs = cs_coll.find_one({"_id": cs__id })
                cs_id = cs.get("id", "NA")

                cnv_chro_stats = cs.get("cnv_chro_stats", False)
                cnv_statusmaps = cs.get("cnv_statusmaps", False)

                if cnv_chro_stats is False or cnv_statusmaps is False:
                    continue

                p_o = {
                    "dataset_id": ds_id,
                    "callset_id": cs_id,
                    "biosample_id": cs.get("biosample_id", "NA"),
                    "cnv_chro_stats": cs.get("cnv_chro_stats", {}),
                    "cnv_statusmaps": cs.get("cnv_statusmaps", {}),
                    "probefile": callset_guess_probefile_path(cs, self.byc),
                    "variants": []
                }
                if r_no == 1 and p_o["probefile"] is not False:
                    p_o.update({"cn_probes": ByconBundler(self.byc).read_probedata_file(p_o["probefile"]) })

                v_q = {"callset_id": cs_id}

                for v in var_coll.find(v_q):
                    p_o["variants"].append(ByconVariant(self.byc).byconVariant(v))

                results.append(p_o)

        plot_data_bundle = {"callsets_variants_bundles": results}
        ByconPlot(self.byc, plot_data_bundle).svg_response()


    # -------------------------------------------------------------------------#

    def __check_datasets_results_histoplot_delivery(self):
        if not "histo" in self.output:
            return

        f_d = self.filter_definitions
        f_s_t = self.form_data.get("plot_group_by", "___none___")

        interval_sets = []

        for ds_id, ds_res in self.datasets_results.items():
            if not "callsets._id" in ds_res:
                continue
            mongo_client = MongoClient(host=environ.get("BYCON_MONGO_HOST", "localhost"))
            bios_coll = mongo_client[ds_id]["biosamples"]
            cs_coll = mongo_client[ds_id]["callsets"]

            f_s_dists = []
            f_s_k = ""

            if f_s_t in f_d.keys():
                if not "biosamples._id" in ds_res:
                    continue
                bios_q_v = ds_res["biosamples._id"].get("target_values", [])
                if len(bios_q_v) < 1:
                    continue

                f_s_k = f_d[f_s_t].get("db_key", "___none___")
                f_s_p = f_d[f_s_t].get("pattern", False)
                f_s_q = {"_id": {"$in": bios_q_v}}
                f_s_dists = bios_coll.distinct(f_s_k, f_s_q)
                if f_s_p is not False:
                    r = re.compile(f_s_p)
                    f_s_dists = list(filter(lambda d: r.match(d), f_s_dists))

                for f_s_id in f_s_dists:

                    bios_id_q = {"$and": [
                        {f_s_k: f_s_id},
                        {"_id": {"$in": bios_q_v}}
                    ]}

                    bios_ids = bios_coll.distinct("id", bios_id_q)
                    cs__ids = cs_coll.distinct("_id", {"biosample_id": {"$in": bios_ids}})
                    r_no = len(cs__ids)
                    if r_no > self.limit:
                        cs__ids = return_paginated_list(cs__ids, self.skip, self.limit)

                    label = f"Search Results (subset {f_s_id})"

                    iset = callset__ids_create_iset(ds_id, label, cs__ids, self.byc)
                    interval_sets.append(iset)

            else:
                cs_r = ds_res["callsets._id"]
                cs__ids = cs_r["target_values"]
                r_no = len(cs__ids)
                # filter for CNV cs before evaluating number
                if r_no > self.limit:
                    cs_cnv_ids = []
                    for _id in cs__ids:
                        cs = cs_coll.find_one({"_id":_id})
                        if "cnv_statusmaps" in cs:
                            cs_cnv_ids.append(_id)
                    cs__ids = cs_cnv_ids
                cs__ids = return_paginated_list(cs__ids, self.skip, self.limit)

                iset = callset__ids_create_iset(ds_id, "Search Results", cs__ids, self.byc)
                interval_sets.append(iset)

        plot_data_bundle = {"interval_frequencies_bundles": interval_sets}
        ByconPlot(self.byc, plot_data_bundle).svg_response()


    # -------------------------------------------------------------------------#

    def __result_sets_save_handovers(self):

        ho_client = MongoClient(host=environ.get("BYCON_MONGO_HOST", "localhost"))
        ho_db = ho_client[ self.byc["config"]["housekeeping_db"] ]
        ho_coll = ho_db[ self.byc["config"][ "handover_coll" ] ]

        for ds_id, d_s in self.datasets_results.items():
            info = {"counts": {}}
            for h_o_k, h_o in d_s.items():
                if not "target_values" in h_o:
                    continue
                h_o_size = sys.getsizeof(h_o["target_values"])
                prdbug(self.byc, f'Storage size for {ds_id}.{h_o_k}: {h_o_size / 1000000}Mb')
                if h_o_size < 15000000:
                    ho_coll.update_one( { "id": h_o["id"] }, { '$set': h_o }, upsert=True )

        ho_client.close()

        return


    # -------------------------------------------------------------------------#

    def __create_empty_result_sets(self):
        r_set = object_instance_from_schema_name(self.byc, "beaconResultsets", "definitions/ResultsetInstance")
        r_sets = []
        for ds_id in self.byc.get("dataset_ids", []):
            ds_rset = r_set.copy()
            ds_rset.update({
                "id": ds_id,
                "set_type": "dataset",
                "results_count": 0,
                "exists": False
                # "info": {"counts": {}}
            })
            r_sets.append(ds_rset)

        self.result_sets = r_sets

        return


    # -------------------------------------------------------------------------#

    def __retrieve_datasets_results(self):
        for i, r_set in enumerate(self.result_sets):
            ds_id = r_set["id"]
            ds_res = execute_bycon_queries(ds_id, self.record_queries, self.byc)
            self.datasets_results.update({ds_id: ds_res})

        return


    # -------------------------------------------------------------------------#

    def __retrieve_datasets_data(self):
        if "variants" in self.data_collection:
            return

        for ds_id, ds_results in self.datasets_results.items():

            if self.handover_key not in ds_results.keys():
                continue

            res = ds_results.get(self.handover_key, {})
            q_k = res.get("target_key", "_id")
            q_db = res.get("source_db", "___none___")
            q_coll = res.get("target_collection", "___none___")
            q_v_s = res.get("target_values", [])
            q_v_s = return_paginated_list(q_v_s, self.skip, self.limit)

            mongo_client = MongoClient(host=environ.get("BYCON_MONGO_HOST", "localhost"))
            data_coll = mongo_client[ q_db ][ q_coll ]

            r_s_res = []
            for q_v in q_v_s:
                o = data_coll.find_one({q_k: q_v })
                r_s_res.append(o)

            self.datasets_data.update({ds_id: r_s_res})

        return


    # -------------------------------------------------------------------------#

    def __retrieve_variants_data(self):
        if not "variants" in self.data_collection:
            return

        for ds_id, ds_results in self.datasets_results.items():

            mongo_client = MongoClient(host=environ.get("BYCON_MONGO_HOST", "localhost"))
            data_db = mongo_client[ ds_id ]
            v_coll = mongo_client[ ds_id ][ "variants" ]

            r_s_res = []

            if "variants._id" in ds_results:
                for v_id in ds_results["variants._id"]["target_values"]:
                    v = v_coll.find_one({"_id":v_id})
                    r_s_res.append(v)
                self.datasets_data.update({ds_id: r_s_res})
            elif "variants.variant_internal_id" in ds_results:
                for v_id in ds_results["variants.variant_internal_id"]["target_values"]:
                    vs = v_coll.find({"variant_internal_id":v_id})
                    for v in vs:
                        r_s_res.append(v)
                self.datasets_data.update({ds_id: r_s_res})

        return


    # -------------------------------------------------------------------------#

    def __populate_result_sets(self):

        for i, r_set in enumerate(self.result_sets):
            ds_id = r_set["id"]
            ds_res = self.datasets_results.get(ds_id, {})
            r_set.update({"results_handovers": dataset_response_add_handovers(ds_id, self.byc)})
            r_s_res = self.datasets_data.get(ds_id)
            r_s_res = reshape_resultset_results(ds_id, r_s_res, self.byc)
            info = {"counts": {}}
            for h_o_k, h_o in ds_res.items():
                if not "target_count" in h_o:
                    continue
                entity = h_o_k.split('.')[0]
                info["counts"].update({entity: h_o["target_count"]})

            self.result_sets[i].update({
                "info": info,
                "results_count": len(r_s_res),
                "paginated_results_count": len(r_s_res),
                "exists": True if len(r_s_res) > 0 else False,
                "results": r_s_res
            })

        return


