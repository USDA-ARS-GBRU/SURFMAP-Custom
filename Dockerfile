# 1st build stage: base image for ubuntu
#################
FROM ubuntu:22.04 as base_os_ubuntu

# to not the user being asked validations upon install process 
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    fort77 \
    gcc-11 \
    less \
    vim-tiny \
    && rm -rf /var/lib/apt/lists/*



# 2nd build stage: add R
#################
FROM base_os_ubuntu as base_os_with_r

RUN apt-get update && apt-get install -y --no-install-recommends \
    r-base \
    && rm -rf /var/lib/apt/lists/*



# 3rd build stage: add python3.10
#################
FROM base_os_with_r as base_os_with_python

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 \
    python3.10-dev \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*



# 4th build stage: add R library dependencies
#################
FROM base_os_with_python as base_os_with_r_lib
RUN R -e "install.packages(c('optparse', 'data.table', 'mapproj'), repos='https://cloud.r-project.org')"



# 5th build stage (builder): create python virtualenv and install surfmap python package
#################
FROM base_os_with_r_lib as surfmap_builder

WORKDIR /surfmap

# install virtualenv, create one and add its bin directory into PATH
RUN pip install --no-cache-dir virtualenv && \
    virtualenv -p python3.10 .env

ENV PATH=/surfmap/.env/bin:$PATH

# add surfmap packages and setup.py
COPY ./ ./

# install surfmap python library & dependencies
# the [local] extra (numpy, freesasa, pdb2pqr, requests) is required: inside
# the container surfmap always runs the local computation pipeline itself
# (there's no docker-in-docker), regardless of whether the host invoked it
# with `--docker`.
RUN pip install --no-cache-dir -e ".[local]"



# 6th build stage (runtime): slim final image - only what's needed to run surfmap,
# discarding the build toolchain (build-essential, gcc-11, fort77, python3.10-dev)
# that was only required to compile R/Python native extensions above.
#################
FROM ubuntu:22.04 as surfmap_runtime

ENV DEBIAN_FRONTEND=noninteractive

# runtime-only OS deps:
# - r-base: Rscript interpreter used by surfmap's R scripts
# - libgomp1: required at runtime by the compiled data.table extension (built with -fopenmp)
# - python3.10 + python3: interpreter backing the venv copied from the builder stage
#   (the venv's `python` symlink resolves via /usr/bin/python3, provided by the python3 package)
RUN apt-get update && apt-get install -y --no-install-recommends \
    r-base \
    libgomp1 \
    python3.10 \
    python3 \
    less \
    vim-tiny \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /surfmap

# copy APBS in /surfmap
COPY softwares/APBS-3.4.1.Linux APBS/

# set env vars for APBS
ENV APBS=/surfmap/APBS
ENV LD_LIBRARY_PATH=$APBS/lib
ENV PATH=$APBS/bin:$PATH

# compiled R packages (optparse, data.table, mapproj + their dependencies) from the builder stage
COPY --from=surfmap_builder /usr/local/lib/R/site-library /usr/local/lib/R/site-library

# surfmap source (required since the python package is installed in editable mode)
COPY ./ ./

# python virtualenv with all compiled wheels (freesasa, numpy, pandas, pdb2pqr, ...) from the builder stage
COPY --from=surfmap_builder /surfmap/.env /surfmap/.env

ENV PATH=/surfmap/.env/bin:$PATH

# create surfmap group and user, non-interactively (from https://github.com/dnaprawa/dockerfile-best-practices#run-as-a-non-root-user)
RUN adduser --disabled-password --gecos "" surfmap && \
    # adduser defaults to a 750 home dir, which blocks *any* other uid from
    # even traversing into it - since surfmap/lib/docker.py bind-mounts the
    # host's input/output directories under /home/surfmap, this silently
    # breaks --docker for every host uid other than surfmap's own (1000)
    # (e.g. CI runners, shared servers), regardless of the mounted paths'
    # own permissions. Open up traversal (execute bit) for all.
    chmod o+rx /home/surfmap

# go to home surfmap
WORKDIR /home/surfmap

# run container as surfmap user and add input & output dirs
USER surfmap
RUN mkdir input output

# default entrypoint so `docker run <image>` is usable standalone
CMD ["surfmap", "--help"]

