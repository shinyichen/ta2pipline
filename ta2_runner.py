import sys
import os
from gen_event_clusters import gen_event_clusters
kg_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'gaia-knowledge-graph/update_kg')
sys.path.append(kg_path)
from Updater import Updater
from datetime import datetime
import papermill as pm
from shutil import copyfile
import configparser


if __name__ == '__main__':

    # ----inputs----
    endpoint = 'http://gaiadev01.isi.edu:7200/repositories'
    wikidata_sparql_endpoint = 'https://dsbox02.isi.edu:8888/bigdata/namespace/wdq/sparql'
    repo_src = 'jchen-test-ta1'
    repo_dst = 'jchen-test-ta2'
    graph = 'http://www.isi.edu/001'
    version = '001'
    delete_existing_clusters = False
    outdir = '/nas/home/jchen/store_data/' + repo_dst
    kg_tab_dir_path = '/nas/gaia/corpora/LDC2019E43_AIDA_Phase_1_Evaluation_Reference_Knowledge_Base/data/'
    cluster_nb = 'er-rpi.ipynb'
    kernel = 'venv'
    # ---------------

    try:
        params_file = sys.argv[1]
    except IndexError:
        print('Error: input parameter file required')
        sys.exit(1)

    config = configparser.ConfigParser()
    config.read(params_file)
    endpoint = config['DEFAULT']['endpoint']
    wikidata_sparql_endpoint = config['DEFAULT']['wikidata_sparql_endpoint']
    kg_tab_dir_path = config['DEFAULT']['kg_tab_dir_path']
    repo_src = config['DEFAULT']['repo_src']
    repo_dst = config['DEFAULT']['repo_dst']
    graph = config['DEFAULT']['graph']
    version = config['DEFAULT']['version']
    delete_existing_clusters = config['DEFAULT'].getboolean('delete_existing_clusters')
    outdir = config['DEFAULT']['outdir']
    cluster_nb = config['DEFAULT']['cluster_nb']
    kernel = config['DEFAULT']['kernel_name']

    endpoint_src = endpoint + '/' + repo_src
    endpoint_dst = endpoint + '/' + repo_dst

    print("Endpoint: ", endpoint)
    print("Src Repository: ", repo_src)
    print("Dst Repository: ", repo_dst)
    print("Graph: ", graph)
    print("Version:", version)
    print("Delete existing clusters: ", delete_existing_clusters)
    print("Output directory: ", outdir)
    print("Using clustering notebook: ", cluster_nb)

    if not os.path.isdir(outdir):
        os.makedirs(outdir)

    print('Generating dataframe... ', datetime.now().isoformat())
    pm.execute_notebook(
        'GenerateDataframe2019.ipynb',
        outdir + '/GenerateDataframe2019.out.ipynb',
        parameters=dict(endpoint_url=endpoint, wikidata_sparql_endpoint=wikidata_sparql_endpoint, 
                        repo=repo_src, version=version, store_data_dir=outdir, add_origin=False),
        kernel_name=kernel
    )

    print('Augmenting dataframe with translation columns... ', datetime.now().isoformat())
    pm.execute_notebook(
        'EntityTranslCols.ipynb',
        outdir + '/EntityTranslCols.out.ipynb',
        parameters=dict(repo=repo_src, version=version, store_data_dir=outdir),
        kernel_name=kernel
    )

    print('Generating entity clusters... ', datetime.now().isoformat())
    pm.execute_notebook(
        cluster_nb,
        outdir + '/er.out.ipynb',
        parameters=dict(input_df_path=outdir + '/entity_trans_all_' + version + '.h5',
                        repo_name=repo_src,
                        version=version,
                        kg_tab_dir_path=kg_tab_dir_path,
                        output_path=outdir + '/entity_clusters_' + version + '.jl'),
        kernel_name=kernel
    )

    print('Generating event clusters... ', datetime.now().isoformat())
    gen_event_clusters(endpoint_src, outdir + '/event_clusters_' + version + '.jl')

    print('Insert into GraphDB... ', datetime.now().isoformat())
    up = Updater(endpoint_src, endpoint_dst, repo_dst, outdir, graph, True)
    up.run_all(delete_existing_clusters=delete_existing_clusters,
               entity_clusters='entity_clusters_' + version + '.jl',
               event_clusters='event_clusters_' + version + '.jl')
