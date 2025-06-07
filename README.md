# FloodSentry AI: Sistema de Previsão de Risco de Inundação 🌊

![Python Version](https://img.shields.io/badge/Python-3.7%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![R Project](https://img.shields.io/badge/R-Project-1E90FF?style=flat-square&logo=R&logoColor=white)
![License](https://img.shields.io/badge/License-All%20Rights%20Reserved-lightgrey?style=flat-square)
![Documentation](https://img.shields.io/badge/Docs-In%20README-brightgreen?style=flat-square)

Este projeto, FloodSentry AI, foi desenvolvido para a competição Global Solution 2025.1 da FIAP. O sistema utiliza dados geoespaciais e Machine Learning para prever o impacto de inundações urbanas. Embora tenha sido treinado e validado inicialmente com dados do evento de inundação de maio de 2024 em Porto Alegre, RS, Brasil, o FloodSentry AI foi concebido como um Produto Mínimo Viável (MVP) com uma arquitetura que visa ser adaptável para análise de risco em outras cidades, mediante a utilização de dados locais análogos.

---

## 🎯 Visão Geral

O projeto FloodSentry AI tem como objetivo principal desenvolver um modelo de previsão de risco de inundação para áreas urbanas, com um sistema de alerta que pode ser emitido via ESP32. O fluxo de trabalho consiste em três etapas principais:

1.  **Preparação de Dados**: Coleta e processamento de dados geoespaciais relevantes para a área de estudo (ex: Porto Alegre como estudo de caso inicial), como modelo digital de elevação (DEM), dados de hidrografia (OpenStreetMap), e manchas de inundação históricas/simuladas. Features como elevação e distância aos rios são calculadas.
2.  **Treinamento do Modelo**: Utilização dos dados preparados para treinar um modelo de Regressão Logística. O modelo aprende a relação entre as características geográficas e a ocorrência de inundações, visando uma metodologia que possa ser replicada.
3.  **Predição de Risco**: Aplicação do modelo treinado para classificar Pontos de Interesse (POIs) específicos quanto ao seu risco de inundação (Baixo ou Alto Risco), sendo o ESP32 (simulado em Wokwi.com) um componente para demonstrar o alerta.

A solução visa atender ao desafio da Global Solution de desenvolver uma solução digital baseada em dados reais, capaz de prever, monitorar ou mitigar os impactos de eventos naturais extremos.

---

## ✨ Funcionalidades Principais

* **Geração de Grid e Extração de Features**: Criação de um grid de pontos sobre a área de estudo e extração de elevação (DEM) e cálculo de distância a corpos d'água (OSM).
* **Processamento de Dados Geoespaciais**: Manipulação de arquivos raster (GeoTIFF) e vetoriais (GeoPackage) utilizando bibliotecas como `geopandas` e `rasterio`.
* **Treinamento de Modelo de Classificação**: Implementação de um modelo de Regressão Logística com `scikit-learn`, incluindo tratamento para classes desbalanceadas (`class_weight='balanced'`).
* **Avaliação de Modelo Customizada**: Avaliação do modelo utilizando um limiar de decisão ajustável para otimizar a classificação de risco.
* **Predição em Pontos de Interesse (POIs)**: Capacidade de carregar o modelo treinado e realizar predições para locais específicos.
* **Alerta via ESP32**: Simulação de um sistema de alerta comunitário utilizando ESP32 (em Wokwi.com) com sensores (simulados) e atuadores (LED/buzzer), comunicando-se via MQTT.
* **Arquitetura Pensada para Adaptação**: Embora validado com dados de Porto Alegre, o MVP busca uma estrutura que possa ser adaptada para outras cidades com dados de entrada equivalentes.
* **Modularidade**: Código organizado em scripts distintos para cada etapa do processo (preparação, treinamento, predição).
* **(Opcional para Pódio)**: Integração com Banco de Dados (SQLite), Análises em R e serviços Google Cloud Platform (Vertex AI, BigQuery).

---

## 📁 Estrutura de Arquivos do Projeto

* `Fase_4/Global Solution/`
    * `Include/`
        * *Diretório para arquivos de inclusão (conteúdo não detalhado).*
    * `Lib/`
        * *Diretório para bibliotecas (conteúdo não detalhado).*
    * `dados_osm_porto_alegre.gpkg`
        * *Exemplo de dados vetoriais de hidrografia (OpenStreetMap) para o estudo de caso de Porto Alegre.*
    * `dados_porto_alegre.qgz`
        * *Exemplo de Projeto QGIS para visualização e análise dos dados geoespaciais de Porto Alegre.*
    * `dados_treinamento_flood_sentry.csv`
        * *Dataset tabular gerado pelo script de preparação (ex: com dados de Porto Alegre), usado para treinar o modelo.*
    * `Global Solution.Rproj`
        * *Projeto RStudio, para análises estatísticas ou visualizações complementares em R (componente para o pódio).*
    * `mancha_inundacao_porto_alegre.tif`
        * *Exemplo de Raster da mancha de inundação (histórica ou simulada, ex: de Porto Alegre) usada como variável alvo.*
    * `modelo_regressao_logistica_flood_sentry.pkl`
        * *Arquivo do modelo de Regressão Logística treinado e serializado.*
    * `preparar_dados_treinamento.py`
        * *Script Python para processar dados brutos (ex: DEM, OSM, mancha de inundação) e gerar o dataset de treinamento.*
    * `prever_risco.py`
        * *Script Python para carregar o modelo treinado e prever o risco em POIs.*
    * `pyvenv.cfg`
        * *Arquivo de configuração para um ambiente virtual Python (indica o uso de venv).*
    * `README.md`
        * *Arquivo de documentação do projeto (este arquivo).*
    * `srtm_porto_alegre.tif`
        * *Exemplo de Modelo Digital de Elevação (DEM) para a área de estudo (ex: SRTM para Porto Alegre).*
    * `srtm_porto_alegre.tif.aux.xml`
        * *Arquivo auxiliar para o raster DEM (metadados).*
    * `treinar_modelo.py`
        * *Script Python para treinar o modelo de Machine Learning.*

---

## 📊 Fontes de Dados Utilizadas (Exemplificadas com Porto Alegre)

Para o desenvolvimento e validação inicial do FloodSentry AI, foram utilizados dados do evento de inundação de maio de 2024 em Porto Alegre. A aplicação do sistema em outras localidades exigiria a obtenção de dados análogos para a nova área de interesse. As fontes de dados exemplificadas incluem:

* **Modelo Digital de Elevação (DEM)**: Ex: `srtm_porto_alegre.tif`. Fornece dados de altitude. Para Porto Alegre, SRTM GL1 (30m) foi considerado.
* **Dados de Hidrografia (Rios/Corpos d'água)**: Ex: `dados_osm_porto_alegre.gpkg` (camada `rios_linhas_POA`), extraído do OpenStreetMap. Utilizado para calcular a distância dos pontos aos rios.
* **Mancha de Inundação (Ground Truth)**: Ex: `mancha_inundacao_porto_alegre.tif`. Raster que define as áreas inundadas. Para Porto Alegre, dados do Copernicus EMS (ativação EMSR720) e NASA Disasters Mapping Portal (DSWx-HLS) foram referenciados.
* **Dados de Infraestrutura Urbana (Opcional, para detalhamento)**: Ex: Edificações e estradas do OpenStreetMap.
* **Dados de Precipitação/Nível de Água (Sensor Simulado)**: Para o MVP, o ESP32 simula um sensor de chuva (botão) ou nível de água (ultrassônico HC-SR04).

A FIAP incentiva o uso de dados análogos aos do `disasterscharter.org`.

---

## 🤖 Detalhes do Modelo

* **Algoritmo**: Regressão Logística (`sklearn.linear_model.LogisticRegression`) como modelo base para o MVP. Modelos mais avançados como RandomForest ou XGBoost podem ser considerados para o pódio.
* **Features (Exemplo)**:
    * `longitude` (Coordenada X)
    * `latitude` (Coordenada Y)
    * `elevation` (Elevação do terreno, do DEM)
    * `distance_to_river` (Distância ao corpo d'água mais próximo, do OSM)
    * (Para pódio/avançado: declividade, tipo de uso do solo, etc.)
* **Variável Alvo**: `is_flooded` (0 para não inundado, 1 para inundado), derivada da mancha de inundação de referência.
* **Considerações**:
    * O modelo é treinado com `class_weight='balanced'` para mitigar o impacto de classes desbalanceadas.
    * Um limiar de decisão customizado (default: `0.4` nos scripts) é aplicado sobre as probabilidades preditas para classificar o risco.
    * O input do sensor ESP32 (nível de água/chuva) atua como um gatilho para a execução da análise de risco ou como um fator de ponderação.

---

## 🛠️ Tecnologias e Dependências

* **Python** (versão 3.7 ou superior recomendada)
* **Bibliotecas Python Principais**:
    * `pandas`: Para manipulação de dados tabulares.
    * `numpy`: Para operações numéricas.
    * `scikit-learn`: Para o treinamento e avaliação do modelo de Machine Learning.
    * `joblib`: Para serialização (salvar/carregar) do modelo treinado.
    * `geopandas`: Para manipulação de dados geoespaciais vetoriais.
    * `rasterio`: Para manipulação de dados geoespaciais raster.
    * `shapely`: Para operações geométricas.
    * `paho-mqtt`: Para comunicação MQTT com o ESP32.
* **Hardware Simulado**: ESP32 (em Wokwi.com) com sensor simulado (HC-SR04 ou botão) e atuadores (LED/Buzzer).
* **Ambiente Virtual**: Recomenda-se o uso de um ambiente virtual Python (o arquivo `pyvenv.cfg` sugere que `venv` pode estar em uso).
* **Software Auxiliar (Opcional para execução dos scripts Python, mas útil para análise)**:
    * **QGIS**: Para visualização e exploração dos dados geoespaciais.
    * **R / RStudio**: Para análises estatísticas ou desenvolvimento complementar (para o pódio).
* **(Opcional para Pódio)**:
    * **SQLite**: Banco de dados local.
    * **Google Cloud Platform (GCP)**: Vertex AI, BigQuery.

---

## ⚙️ Instalação e Configuração

1.  **Clone o Repositório** (se aplicável):
    ```bash
    # git clone <url-do-repositorio>
    # cd Fase_4/Global Solution
    ```

2.  **Crie e Ative um Ambiente Virtual Python**:
    ```bash
    python -m venv venv
    # No Windows:
    # venv\Scripts\activate
    # No macOS/Linux:
    # source venv/bin/activate
    ```

3.  **Instale as Dependências**:
    Crie um arquivo `requirements.txt` com o seguinte conteúdo:
    ```txt
    pandas
    numpy
    scikit-learn
    joblib
    geopandas
    rasterio
    shapely
    paho-mqtt
    ```
    E então instale-as:
    ```bash
    pip install -r requirements.txt
    ```
    *Nota*: A instalação de `geopandas` e `rasterio` pode ter dependências de sistema (como GDAL). Consulte a documentação oficial dessas bibliotecas para instruções de instalação específicas para o seu sistema operacional caso encontre problemas.

4.  **Estrutura de Dados**: Certifique-se de que os arquivos de dados brutos necessários para a localidade escolhida (ex: DEM, dados de hidrografia, mancha de inundação de referência) estejam presentes na pasta raiz do projeto ou em um local acessível pelos scripts. Para o estudo de caso de Porto Alegre, os nomes dos arquivos são exemplificados na estrutura de arquivos.

---

## 🚀 Como Usar

Execute os scripts na seguinte ordem:

1.  **Preparar Dados de Treinamento**:
    Este script processa os dados geoespaciais brutos da área de estudo e gera o arquivo `dados_treinamento_flood_sentry.csv`.
    ```bash
    python preparar_dados_treinamento.py
    ```

2.  **Treinar o Modelo de Machine Learning**:
    Este script carrega o dataset de treinamento e treina o modelo de Regressão Logística, salvando-o como `modelo_regressao_logistica_flood_sentry.pkl`.
    ```bash
    python treinar_modelo.py
    ```

3.  **Prever Risco de Inundação**:
    Este script carrega o modelo treinado e realiza predições para Pontos de Interesse (POIs) definidos internamente no script, simulando também a interação com o ESP32 (Wokwi). Os resultados são exibidos no console.
    ```bash
    python prever_risco.py
    ```
    *Nota*: Você pode customizar os POIs diretamente no arquivo `prever_risco.py` antes da execução. Para uma nova cidade, o modelo `*.pkl` precisaria ser treinado com dados daquela cidade, ou o MVP atual ser usado como uma prova de conceito da metodologia.

---

## 🔮 Melhorias Futuras (Sugestões)

* **Generalização e Validação**: Testar e validar a adaptabilidade do sistema para diferentes cidades com diferentes características e fontes de dados.
* **Fonte de Dados para POIs**: Permitir que os POIs para predição sejam carregados de um arquivo externo (CSV, GeoJSON).
* **Integração de Dados de Sensores em Tempo Real**: Além da simulação, integrar com dados reais de sensores (requer hardware e infraestrutura).
* **Modelos Mais Avançados**: Experimentar com outros algoritmos de Machine Learning (ex: Random Forest, Gradient Boosting, Redes Neurais) para buscar melhorias na performance da predição.
* **Validação Robusta**: Implementar técnicas de validação cruzada mais sofisticadas e otimização de hiperparâmetros.
* **Interface de Usuário**: Desenvolver uma interface gráfica (web ou desktop) para facilitar a interação com o sistema.
* **API para Predições**: Expor a funcionalidade de predição através de uma API.
* **Aprofundamento na Integração GCP**: Expandir o uso de Vertex AI Pipelines para MLOps, Model Monitoring, etc.

---

## 📄 Licença

Este projeto foi desenvolvido para fins acadêmicos no âmbito da FIAP Global Solution 2025.1. Todos os direitos relativos a este código e seus componentes são reservados ao(s) autor(es).

**Copyright © 2025 Omar Calil Abrão Mustafá Assem**

Nenhuma parte deste projeto pode ser reproduzida, distribuída ou transmitida de qualquer forma ou por qualquer meio, incluindo fotocópia, gravação ou outros métodos eletrônicos ou mecânicos, sem a permissão prévia por escrito do(s) autor(es), exceto no caso de breves citações incorporadas em revisões críticas e certos outros usos não comerciais permitidos pela lei de direitos autorais.

Para consultas sobre permissões, pode-se contatar o autor principal através das informações de perfil na plataforma FIAP ou e-mail fornecido no cadastro da Global Solution (ocama12@gmail.com).

---
