# FIAP - Faculdade de Informática e Administração Paulista

<p align="center">
<a href="https://www.fiap.com.br/"><img src="assets/logo-fiap.png" alt="FIAP - Faculdade de Informática e Administração Paulista" width="40%"></a>
</p>

<br>

# Global Solution - 1º Semestre

## Fase 4 – Capítulo 1  
Período: 26/05/2025 a 06/06/2025

## 👨‍🎓 Integrantes:
- Deivisson Gonçalves Lima – RM565095 – [deivisson.engtele@gmail.com](mailto:deivisson.engtele@gmail.com)
- Omar Calil Abrão Mustafá Assem – RM561375 – [ocama12@gmail.com](mailto:ocama12@gmail.com)
- Paulo Henrique de Sousa – RM564262 – [pauloo.sousa16@outlook.com](mailto:pauloo.sousa16@outlook.com)
- Renan Danilo dos Santos Pereira – RM566175 – [renansantos4978@gmail.com](mailto:renansantos4978@gmail.com)

## 👩‍🏫 Professores:
### Tutor(a):
- Lucas Gomes Moreira  
### Coordenador(a):
- André Godoi Chiovato  

---

## 📜 Introdução

Este projeto, **FloodSentry AI**, foi desenvolvido no âmbito da Global Solution 2025.1 com o objetivo de prever e alertar riscos de inundações urbanas por meio de análise de dados geoespaciais e técnicas de aprendizado de máquina. Utilizando como estudo de caso a cidade de Porto Alegre (evento de maio de 2024), a solução oferece um modelo de previsão e simulação de alertas integrados a sensores ESP32, com possibilidade de adaptação para outras localidades e desastres.

---

## 🔧 Desenvolvimento

### 💡 Problema escolhido
Inundações urbanas e a ausência de sistemas preventivos de alerta em tempo hábil para comunidades em risco.

### 🌐 Arquitetura da solução
- Coleta e processamento de dados geoespaciais (DEM, rios, manchas de inundação).
- Criação de grid e extração de features como elevação e distância a rios.
- Treinamento de modelo de regressão logística para classificar risco.
- Simulação de sensores com ESP32 para envio de alerta via MQTT.
- Organização modular dos scripts Python para cada etapa do pipeline.

## 📊 Fontes de Dados Utilizadas (Exemplificadas com Porto Alegre)

Para o desenvolvimento e validação inicial do FloodSentry AI, foram utilizados dados do evento de inundação de maio de 2024 em Porto Alegre. A aplicação do sistema em outras localidades exigiria a obtenção de dados análogos para a nova área de interesse. As fontes de dados exemplificadas incluem:

* **Modelo Digital de Elevação (DEM)**: Ex: `srtm_porto_alegre.tif`. Fornece dados de altitude. Para Porto Alegre, SRTM GL1 (30m) foi considerado.
* **Dados de Hidrografia (Rios/Corpos d'água)**: Ex: `rios_porto_alegre.gpkg`, extraído do OpenStreetMap. Utilizado para calcular a distância dos pontos aos rios.
* **Mancha de Inundação (Ground Truth)**: Ex: `manchas_inundacao.gpkg`. Raster que define as áreas inundadas. Para Porto Alegre, dados do Copernicus EMS (ativação EMSR720) e NASA Disasters Mapping Portal (DSWx-HLS) foram referenciados.
* **Dados de Infraestrutura Urbana (Opcional)**: Edificações e estradas do OpenStreetMap, caso desejado para uso futuro.
* **Dados de Precipitação/Nível de Água (Sensor Simulado)**: Para o MVP, o ESP32 simula um sensor de chuva (botão) ou nível de água (ultrassônico HC-SR04).

A FIAP incentiva o uso de dados análogos aos disponíveis no portal [https://disasterscharter.org](https://disasterscharter.org), que também podem ser utilizados para novos experimentos.

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

### 📦 Tecnologias utilizadas
- Python 3.x
- ESP32 com sensor simulado (ultrassônico ou botão)
- Pandas, Scikit-learn, Geopandas, Rasterio
- MQTT (via Paho MQTT)
- VS Code + PlatformIO
- Dados de [disasterscharter.org](https://disasterscharter.org)
- Git e GitHub

### 🤖 Machine Learning
- Tipo de modelo: Regressão Logística
- Entradas: elevação, distância a rios, latitude, longitude
- Saídas: risco de inundação (0 = baixo, 1 = alto)

---

## ✅ Resultados Esperados

- Classificação automatizada de risco para pontos da cidade.
- Acionamento de alerta (LED/buzzer) via ESP32 simulando notificação à comunidade.
- Metodologia replicável para outras cidades.

---

## 🎓 Conclusão

O projeto FloodSentry AI representa uma aplicação prática de conceitos estudados nas disciplinas de lógica computacional, estrutura de dados, aprendizado de máquina e sistemas embarcados. A solução proposta demonstra como dados reais e sensores podem ser integrados para gerar impacto positivo na prevenção de desastres naturais, cumprindo os objetivos da Global Solution.

---

## 📁 Estrutura de Pastas

```
📁 Global Solution
 ┣ 📂 assets
 ┣ 📂 data
 ┃ ┗ 📂 raw
 ┃    ┣ 📜 srtm_porto_alegre.tif
 ┃    ┣ 📜 rios_porto_alegre.gpkg
 ┃    ┗ 📜 manchas_inundacao.gpkg
 ┣ 📂 docs
 ┣ 📂 output
 ┣ 📂 src
 ┣ 📜 Global Solution.Rproj
 ┣ 📜 README.md
 ┗ 📜 requirements.txt
```

📦 **Atenção: Os arquivos da pasta `/data/raw` (dados geoespaciais brutos) estão disponíveis via Google Drive devido ao tamanho exceder o limite do GitHub.**

🔗 Link para acesso: [Google Drive - FloodSentry Dataset](https://drive.google.com/drive/folders/1hjR-KTJmBPBI-zDuT2W02kejKWZd1FFY?usp=drive_link)

📌 **Para obter acesso:**
1. Clique no link acima;
2. Solicite permissão de visualização;
3. O administrador do repositório concederá o acesso mediante solicitação.

---

## 🔗 Repositório GitHub

https://github.com/limadeivisson/global-solution-fase4-2025

---

## 🎥 Vídeo da Demonstração

- Link YouTube (não listado): [inserir aqui o link do vídeo com a frase “QUERO CONCORRER” no início]

---

## 📄 Licença

Projeto acadêmico desenvolvido para a FIAP – Global Solution 2025.1.
Todos os direitos reservados aos autores.