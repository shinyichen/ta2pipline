import numpy as np
import pandas as pd
import os
import io
from copy import deepcopy
import json
import csv
import sys
import random
import string
from collections import defaultdict
import glob
import warnings
from config import config, get_logger
from operator import itemgetter
import rltk


logger = get_logger('clusterer')

def flatten(list_, remove_none=True):
    # flatten([1,2,3,4, [2,2,4],[13,[2,3,2]]])
    if isinstance(list_, (list, tuple)):
        ret = []
        for l in list_:
            for n in flatten(l):
                ret.append(n)
        return ret
    else:
        if remove_none and not list_:
            return []
        return [list_]


def top_score_indices(list_, num):
    return sorted(range(len(list_)), key=lambda i: list_[i])[-num:]


@rltk.set_id('e')
class GaiaRecord(rltk.AutoGeneratedRecord):
    # Index(['Unnamed: 0', 'e', 'name', 'type', 'target', 'target_score',
    #        'target_type', 'target_name', 'fbid', 'fbid_score_avg',
    #        'fbid_score_max', 'wikidata', 'wikidata_label_en', 'wikidata_label_ru',
    #        'wikidata_label_uk', 'wikidata_description_en',
    #        'wikidata_description_ru', 'wikidata_description_uk',
    #        'wikidata_alias_en', 'wikidata_alias_ru', 'wikidata_alias_uk',
    #        'infojust_confidence', 'informative_justification', 'just_confidence',
    #        'justified_by', 'source'],

    # @rltk.cached_property
    # def augmented_names(self):
    #     ret = []
    #     targets = self.raw_object['target']
        # if targets:
        #     for t in targets:
        #         kb_prefix, t = t.split(':')
        #         if kb_prefix != 'LDC2019E43':
        #             ret.append([])
        #             continue
        #
        #         names = kb_names.get(t)
        #         if names:
        #             ret.append(names['names'])
        #         else:
        #             ret.append([])
        #     return ret

    @rltk.cached_property
    def selected_wikidata(self):
        if self.fbid_score_avg:
            selected_indice = top_score_indices(self.fbid_score_avg, 1)
            return flatten(itemgetter(*selected_indice)(self.wikidata))

    @rltk.cached_property
    def selected_fbid(self):
        if self.fbid_score_avg:
            selected_indice = top_score_indices(self.fbid_score_avg, 1)
            return flatten(itemgetter(*selected_indice)(self.fbid))

    @rltk.cached_property
    def selected_target(self):
        if self.target_score:
            selected_indice = top_score_indices(self.target_score, 1)
            return flatten(itemgetter(*selected_indice)(self.target))

    @rltk.cached_property
    def selected_wikidata_label_en(self):
        if self.fbid_score_avg:
            selected_indice = top_score_indices(self.fbid_score_avg, 1)

            # wikidata labels and translation (based on freebase)
            if self.wikidata_label_en:
                return flatten(itemgetter(*selected_indice)(self.wikidata_label_en))

    #     @property
    @rltk.cached_property
    def concatenated_labels(self):
        ret = []

        # name and translation
        if self.name:
            ret += self.name
        # if self.transl_name:
        #     ret += self.transl_name

        # target labels
        if self.target_score:
            selected_indice = top_score_indices(self.target_score, 1)
            ret += flatten(itemgetter(*selected_indice)(self.target_name))

        if self.fbid_score_avg:
            selected_indice = top_score_indices(self.fbid_score_avg, 1)

            # wikidata labels and translation (based on freebase)
            if self.wikidata_label_en:
                ret += flatten(itemgetter(*selected_indice)(self.wikidata_label_en))
            if self.wikidata_label_ru:
                ret += flatten(itemgetter(*selected_indice)(self.wikidata_label_ru))
            if self.wikidata_label_uk:
                ret += flatten(itemgetter(*selected_indice)(self.wikidata_label_uk))
            # if self.transl_label_ru:
            #     ret += flatten(itemgetter(*selected_indice)(self.transl_label_ru))
            # if self.transl_label_uk:
            #     ret += flatten(itemgetter(*selected_indice)(self.transl_label_uk))

            # wikidata alias and translation
            if self.wikidata_alias_en:
                ret += flatten(itemgetter(*selected_indice)(self.wikidata_label_en))
            if self.wikidata_alias_ru:
                ret += flatten(itemgetter(*selected_indice)(self.wikidata_alias_ru))
            if self.wikidata_alias_uk:
                ret += flatten(itemgetter(*selected_indice)(self.wikidata_alias_uk))
            # if self.transl_alias_ru:
            #     ret += flatten(itemgetter(*selected_indice)(self.transl_alias_ru))
            # if self.transl_alias_uk:
            #     ret += flatten(itemgetter(*selected_indice)(self.transl_alias_uk))

        return set(ret)


# MAX_DISTANCE = 999999
class Cluster(object):
    def __init__(self, ds):
        self.attractive_records = set([])  # contribute to clustering
        self.all_records = set([])
        self.ds = ds
        self.type = None
        self.wd_id = set([])
        self.kb_id = set([])
        self.fb_id = set([])

        self.prototype = None
        self.id_ = self.random_str(10)
        self.full_id = None
        self.feature_entity_id = None

    @staticmethod
    def record_score(r1, r2):
        score = rltk.jaccard_index_similarity(set(r1.concatenated_labels), set(r2.concatenated_labels))
        return score

    @staticmethod
    def random_str(length=32):
        return ''.join([random.choice(string.ascii_letters + string.digits) for _ in range(length)])

    def similarity(self, r):
        #         if r.type != self.type:
        #             return MAX_DISTANCE

        score = max([self.record_score(r, self.ds.get_record(rr)) for rr in self.attractive_records])
        #         if score == 0:
        #             return MAX_DISTANCE
        return score

    def add(self, r, contribute=True):
        if isinstance(r, rltk.Record):
            r = r.id
        if contribute:
            self.attractive_records.add(r)
        self.all_records.add(r)

    def generate(self):
        self.feature_entity_id = deepcopy(self.all_records.pop())
        self.prototype = self.feature_entity_id #+ '-prototype-' + self.id_
        self.full_id = self.feature_entity_id + '-cluster-' + self.id_


def normalize_type(t):
    type_prefix = t.split('.')[0][len('ldcOnt:'):]
    if type_prefix in ('GPE', 'LOC'):
        return 'GeoLoc'
    return type_prefix


def process():

    df_entity = pd.DataFrame()

    logger.info('loading entity dataframes')
    for infile in glob.glob(os.path.join(config['temp_dir'], config['run_name'], '*/*.entity.h5')):
        source = os.path.basename(infile).split('.')[0]
        df_entity = df_entity.append(pd.read_hdf(infile))
    df_entity = df_entity.reset_index(drop=True)
    logger.info('Total number of entities: %d', len(df_entity))
    df_entity['type'] = df_entity['type'].apply(lambda x: x[0])  # only pick the fist type (compatible with old pipeline)
    df_entity_ori = df_entity.copy()

    ### filtering
    logger.info('filtering out some entity types')
    all_types = set(df_entity['type'])
    # all_types = set([t for tu in df_entity['type'] for t in tu])  # multi-type support
    selected_types = filter(lambda x: x.startswith(('ldcOnt:GPE', 'ldcOnt:LOC', 'ldcOnt:ORG', 'ldcOnt:PER')), all_types)
    df_entity = df_entity.loc[df_entity['type'].isin(selected_types)]
    # df_entity = df_entity.loc[[any([t in selected_types for t in tu]) for tu in df_entity['type']]] # multi-type support
    df_entity = df_entity[df_entity['name'].notnull()]
    df_entity = df_entity.where(pd.notnull(df_entity), None)
    df_entity_left = df_entity_ori[~df_entity_ori['e'].isin(df_entity['e'])]

    ### generate rltk components
    logger.info('generating rltk components')
    ds = rltk.Dataset(reader=rltk.DataFrameReader(df_entity), record_class=GaiaRecord)
    bg_kb = rltk.TokenBlocker()
    blocks_kb = bg_kb.block(ds, function_=lambda r: list(r.selected_target) if r.selected_target else ['None'])
    bg_fb = rltk.TokenBlocker()
    blocks_fb = bg_fb.block(ds, function_=lambda r: r.selected_fbid if r.selected_fbid else ['None'])

    ### clustering
    logger.info('clustering entity')
    # build cluster based on type
    all_clusters = []
    for bid, data in blocks_kb.key_set_adapter:
        if bid == 'None':
            continue

        c = Cluster(ds)
        for _, r_id in data:
            r = ds.get_record(r_id)
            for id_ in r.selected_target:
                c.kb_id.add(id_)
            if r.fbid:
                for id_ in r.selected_fbid:
                    c.fb_id.add(id_)
            if r.wikidata:
                for id_ in r.selected_wikidata:
                    c.wd_id.add(id_)
            c.add(r)
        all_clusters.append(c)

    # fb only clusters
    fb_only_clusters = {}
    for bid, data in blocks_fb.key_set_adapter:
        if bid == 'None':
            continue

        fb_only_clusters[bid] = set()
        for _, r_id in data:
            r = ds.get_record(r_id)
            if r.selected_target:
                continue
            fb_only_clusters[bid].add(r_id)
        if len(fb_only_clusters[bid]) == 0:
            del fb_only_clusters[bid]

    for bid, cluster in fb_only_clusters.items():
        c = Cluster(ds)
        for r_id in cluster:
            c.add(r_id)
            r = ds.get_record(r_id)
            if r.fbid:
                for id_ in r.selected_fbid:
                    c.fb_id.add(id_)
            if r.wikidata:
                for id_ in r.selected_wikidata:
                    c.wd_id.add(id_)
        all_clusters.append(c)

    # validation
    for idx, c in enumerate(all_clusters):
        if len(c.kb_id) > 1:
            logger.error('mulitple kb_ids in cluster: %s', c.kb_id)
            break

        kb_ids = set()
        for r_id in c.all_records:
            r = ds.get_record(r_id)
            if r.selected_target:
                for id_ in r.selected_target:
                    kb_ids.add(id_)
        if len(kb_ids) > 1:
            logger.error('mulitple kb_ids in cluster: %s', kb_ids, c.kb_id)
            break

    # split based on types
    all_clusters_splitted = []
    for c in all_clusters:
        types = {}
        for r_id in c.all_records:
            r = ds.get_record(r_id)
            type_ = normalize_type(r.type)
            if type_ not in types:
                cc = Cluster(ds)
                cc.type = type_
                types[type_] = cc

            cc = types[type_]
            cc.add(r_id)
            if r.selected_target:
                for id_ in r.selected_target:
                    cc.kb_id.add(id_)
            if r.selected_fbid:
                for id_ in r.selected_fbid:
                    cc.fb_id.add(id_)
            if r.selected_wikidata:
                for id_ in r.selected_wikidata:
                    cc.wd_id.add(id_)
        for cc in types.values():
            all_clusters_splitted.append(cc)

    # merge singleton
    final_clusters = deepcopy(all_clusters_splitted)
    MIN_SIM = 0.4
    clustered_entity_ids = set([r for c in all_clusters for r in c.all_records])

    for _, e in df_entity['e'].items():
        if e not in clustered_entity_ids:
            added = False
            r = ds.get_record(e)
            r_type = normalize_type(r.type)
            for c in final_clusters:
                sim = c.similarity(r)
                if r_type != c.type:
                    continue
                if sim >= MIN_SIM:
                    c.add(r, contribute=False)
                    added = True

            # still singleton, construct singleton cluster
            if not added:
                c = Cluster(ds)
                c.type = r_type
                c.add(r)
                final_clusters.append(c)

    # filtered-out entities
    # create cluster with fake record
    for _, e in df_entity_left.iterrows():
        c = Cluster(None)
        c.type = normalize_type(e['type'])
        c.add(e['e'], contribute=False)
        final_clusters.append(c)
    logger.info('Total number of clusters: %d', len(final_clusters))

    # create entity to cluster mapping
    entity_to_cluster = defaultdict(list)
    for c in final_clusters:
        for r in c.all_records:
            entity_to_cluster[r].append(c)

    ### generate cluster properties
    logger.info('generating cluster properties')
    for c in final_clusters:
        c.generate()

    ### export
    logger.info('exporting clusters')
    df_entity_cluster = df_entity_ori.copy()
    df_entity_cluster['cluster'] = None
    df_entity_cluster['synthetic'] = False
    for idx, e in df_entity_cluster['e'].items():
        clusters = tuple(set([c.full_id for c in entity_to_cluster[e]]))
        df_entity_cluster.at[idx, 'cluster'] = clusters

    df_prototypes = pd.DataFrame(columns=df_entity_cluster.columns)
    for c in final_clusters:
        p = df_entity_ori[df_entity_ori['e'] == c.feature_entity_id].iloc[0]
        p['synthetic'] = True
        p['cluster'] = tuple([c.full_id])
        p['e'] = c.prototype
        df_prototypes = df_prototypes.append(p)

    df_complete_entity_clusters = df_entity_cluster.append(df_prototypes)
    df_complete_entity_clusters.reset_index(drop=True)

    output_file = os.path.join(config['temp_dir'], config['run_name'], 'entity_cluster.h5')
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        df_complete_entity_clusters.to_hdf(output_file, 'entity', mode='w', format='fixed')
        df_complete_entity_clusters.to_csv(output_file + '.csv')


if __name__ == '__main__':
    argv = sys.argv
    if argv[1] == 'process':
        process()

