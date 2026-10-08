"""geoapps-api: the HTTP contract (ownership rule 5).

It imports geoapps-db and never GeoStack, so no JAX runs in the web process.
Heavy work is submitted as jobs and run by geoapps-workers.
"""
