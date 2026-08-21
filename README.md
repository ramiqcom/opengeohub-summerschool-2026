# Collection of Scripts and Notebooks by Ramadhan for OpenGeoHub Summer School 2026 at ITU, Istanbul

This repository contains many useful and experimental scripts and notebooks that mostly used for hackathon competition topic 1: Aboveground biomass modelling.

This repository can be split into two workflows:

## 1. Notebook

Folder [notebook](notebook) contains Jupyter Notebooks for conversing CSV to parquet, analysis with the basic data, and modelling with extracted dataset.

## 2. Docker Job

Folder [job](job) contains script for running heavy and background task, mostly that need heavy I/O such as compositing satellite imagery, acquiring and tiling canopy height data from external source, and extracting features.

To run this job, you need to check [docker-compose.yml](docker-compse.yml) for available job you can do.
