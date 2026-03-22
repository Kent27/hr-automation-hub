FROM continuumio/miniconda3:latest

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        libcairo2 \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libgdk-pixbuf-2.0-0 \
        libffi-dev \
        shared-mime-info \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY environment.yml .

RUN conda env create -f environment.yml && conda clean -afy

RUN echo "conda activate hr-automation-hub" >> ~/.bashrc
ENV PATH /opt/conda/envs/hr-automation-hub/bin:$PATH

COPY . .

EXPOSE 8090

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090", "--reload", "--timeout-keep-alive", "300"]
