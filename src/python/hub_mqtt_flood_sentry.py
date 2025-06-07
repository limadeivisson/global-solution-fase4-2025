# -*- coding: utf-8 -*-
"""
Hub MQTT para o Projeto FloodSentry AI.

Versão V13.8.2 - Integração DB Completa com Monitoramento do Hub:
- Salva leituras de sensores, análises de POIs e alertas do sistema em um banco SQLite.
- Adiciona registro periódico do status de performance do próprio hub no banco de dados.
- Utiliza o módulo gerenciador_db.py.
- Inclui lógica de retry para a conexão MQTT para maior robustez.
- Mantém traduções, melhorias visuais com Rich e buffer dinâmico.
"""

# --- Importações de Bibliotecas ---
import paho.mqtt.client as mqtt
import time
import os
import json
import joblib
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, MultiLineString, LineString
from shapely.ops import unary_union
from sklearn.preprocessing import StandardScaler
from typing import List, Dict, Any, Optional, Union
import traceback
import logging
from datetime import datetime, timezone
import socket

# Importações da biblioteca Rich
from rich.logging import RichHandler
from rich.console import Console
from rich.table import Table, Column
from rich.panel import Panel
from rich.text import Text
from rich.style import Style
from rich import box

# Importação do nosso módulo de banco de dados
import gerenciador_db

# --- Configuração do Logging com Rich ---
logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, tracebacks_show_locals=False, tracebacks_word_wrap=False, show_path=False, markup=True)]
)
log = logging.getLogger("rich")
console = Console()

# --- Constantes de Configuração ---
MQTT_BROKER_HOST: str = "test.mosquitto.org"
MQTT_BROKER_PORT: int = 1883
MQTT_KEEPALIVE: int = 60
MQTT_CLIENT_ID: str = "FloodSentry_HubPython_OmarAssem_V13_8_2_FullDB"

MAX_MQTT_CONNECT_ATTEMPTS = 3
MQTT_CONNECT_RETRY_DELAY_SECONDS = 10

TOPIC_SENSOR_WATER_LEVEL: str = "fiap/gs/OmarAssem/flood_sentry/sensor/water_level"
TOPIC_SENSOR_RAINFALL: str = "fiap/gs/OmarAssem/flood_sentry/sensor/rainfall"
TOPIC_ESP_CRITICAL_ALERT_STATUS: str = "fiap/gs/OmarAssem/flood_sentry/alert/critical_status"
TOPIC_COMMAND_ALERT_STATUS: str = "fiap/gs/OmarAssem/flood_sentry/command/alert_status"

# --- CAMINHOS DE ARQUIVO ATUALIZADOS ---
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DATA_RAW_DIR = os.path.join(ROOT_DIR, 'data', 'raw')
OUTPUT_MODEL_DIR = os.path.join(ROOT_DIR, 'output', 'model')

MODEL_FILE_NAME: str = "modelo_xgb_slope_curvature_scaled.pkl"
SCALER_FILE_NAME: str = "scaler_slope_curvature_features.pkl"
OSM_GPKG_FILE_NAME: str = "dados_osm_porto_alegre.gpkg"
EDIFICIOS_LAYER_NAME: str = "dados_osm_porto_alegre_edificacoes_poligonos_POA"
ESTRADAS_LAYER_NAME: str = "dados_osm_porto_alegre_estradas_linhas_POA"
RIOS_LAYER_NAME: str = "dados_osm_porto_alegre_rios_linhas_POA"

MODEL_PATH: str = os.path.join(OUTPUT_MODEL_DIR, MODEL_FILE_NAME)
SCALER_PATH: str = os.path.join(OUTPUT_MODEL_DIR, SCALER_FILE_NAME)
OSM_GPKG_PATH: str = os.path.join(DATA_RAW_DIR, OSM_GPKG_FILE_NAME)
# --- FIM DOS CAMINHOS ATUALIZADOS ---

FEATURES_ORDER: List[str] = ['longitude', 'latitude', 'elevation', 'distance_to_river', 'slope', 'curvature']
PREDICTION_THRESHOLD: float = 0.028
SENSOR_DATA_TIMEOUT_SECONDS: int = 35
MODEL_CHECK_INTERVAL_SECONDS: int = 60

RAIO_BUFFER_PADRAO_METERS: int = 200
RAIO_BUFFER_AGUA_MEDIO_METERS: int = 300
RAIO_BUFFER_AGUA_ALTO_METERS: int = 500

CRS_WGS84: str = "EPSG:4326"
CRS_PROJETADO_POA: str = "EPSG:31982"

# --- Variáveis Globais ---
latest_water_level_data: Optional[Dict[str, Any]] = None
timestamp_last_water_data: Optional[float] = None
latest_rainfall_data: Optional[Dict[str, Any]] = None
timestamp_last_rain_data: Optional[float] = None
esp32_critical_alert_is_active: bool = False
esp32_critical_alert_details: Optional[Dict[str, Any]] = None

ml_model_instance: Optional[Any] = None
scaler_instance: Optional[StandardScaler] = None
timestamp_artefatos_carregados: Optional[float] = None
last_artefatos_check_time: float = 0.0

edificios_gdf_metric: Optional[gpd.GeoDataFrame] = None
estradas_gdf_metric: Optional[gpd.GeoDataFrame] = None
rios_gdf_metric: Optional[gpd.GeoDataFrame] = None

msgs_recebidas_counter = 0
alertas_enviados_counter = 0

# --- Funções de Callback MQTT ---
def on_connect(client: mqtt.Client, userdata: Any, flags: Dict[str, Any], rc: int, properties: Optional[mqtt.Properties] = None) -> None:
    if rc == 0:
        log.info(f"Conectado com sucesso ao Broker MQTT: {MQTT_BROKER_HOST} (rc: {mqtt.connack_string(rc)})")
        try:
            client.subscribe(TOPIC_SENSOR_WATER_LEVEL); client.subscribe(TOPIC_SENSOR_RAINFALL); client.subscribe(TOPIC_ESP_CRITICAL_ALERT_STATUS)
            log.info(f"Subscrito aos tópicos de sensores e alertas.")
        except Exception as e: log.error(f"Falha ao subscrever: {e}")
    else: log.error(f"Falha ao conectar ao Broker MQTT. Código (rc): {rc} - {mqtt.connack_string(rc)}")

def on_disconnect(client: mqtt.Client, userdata: Any, rc: int, properties: Optional[mqtt.Properties] = None) -> None:
    log.info(f"Desconectado do Broker MQTT (rc: {rc}).")
    if rc != 0: log.warning("Desconexão inesperada.")

def on_message_water_level(client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage, properties: Optional[mqtt.Properties] = None) -> None:
    global latest_water_level_data, timestamp_last_water_data, msgs_recebidas_counter
    msgs_recebidas_counter += 1
    try:
        payload_str = msg.payload.decode('utf-8'); data = json.loads(payload_str)
        latest_water_level_data = data; timestamp_last_water_data = time.time()
        cat = data.get('level_category', 'N/A')
        style = "green" if cat == "Baixo" else "yellow" if cat == "Medio" else "red" if cat == "Alto" else "white"
        console.print(Text.assemble(Text("SENSOR (Nível da Água): Categoria = "), Text(cat, style=style), Text(f" (Recebido: {time.strftime('%H:%M:%S')})")))
        conn = gerenciador_db.criar_conexao()
        if conn:
            try:
                gerenciador_db.inserir_leitura_sensor(conn, "nivel_agua", cat, dados_brutos=data)
            finally:
                conn.close()
    except Exception as e: log.error(f"Processar msg nível da água: {e}", exc_info=True)

def on_message_rainfall(client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage, properties: Optional[mqtt.Properties] = None) -> None:
    global latest_rainfall_data, timestamp_last_rain_data, msgs_recebidas_counter
    msgs_recebidas_counter += 1
    try:
        payload_str = msg.payload.decode('utf-8'); data = json.loads(payload_str)
        latest_rainfall_data = data; timestamp_last_rain_data = time.time()
        cat = data.get('intensity_category', 'N/A')
        style = "green" if cat in ["Nenhuma", "Leve"] else "yellow" if cat == "Moderada" else "red" if cat == "Pesada" else "white"
        console.print(Text.assemble(Text("SENSOR (Qtd. Chuva): Categoria = "), Text(cat, style=style), Text(f" (Recebido: {time.strftime('%H:%M:%S')})")))
        conn = gerenciador_db.criar_conexao()
        if conn:
            try:
                gerenciador_db.inserir_leitura_sensor(conn, "qtd_chuva", cat, dados_brutos=data)
            finally:
                conn.close()
    except Exception as e: log.error(f"Processar msg chuva: {e}", exc_info=True)

def on_message_esp_critical_alert_status(client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage, properties: Optional[mqtt.Properties] = None) -> None:
    global esp32_critical_alert_is_active, esp32_critical_alert_details, msgs_recebidas_counter
    msgs_recebidas_counter += 1
    try:
        payload_str = msg.payload.decode('utf-8'); data = json.loads(payload_str)
        alert_status = data.get("status", "").upper()
        log_cat_valor = "N/A"
        if alert_status == "ACTIVE":
            esp32_critical_alert_is_active = True; esp32_critical_alert_details = data
            log.critical(f"ALERTA CRÍTICO DO ESP32 ATIVADO !!! Detalhes: {data}")
            log_cat_valor = "ACTIVE"
        elif alert_status == "CLEARED":
            esp32_critical_alert_is_active = False; esp32_critical_alert_details = None
            log.info(f"Alerta crítico do ESP32 NORMALIZADO. Detalhes: {data}")
            log_cat_valor = "CLEARED"
        else:
            log.warning(f"Status de alerta crítico ESP32 desconhecido: {payload_str}")
            log_cat_valor = "DESCONHECIDO"
        conn = gerenciador_db.criar_conexao()
        if conn:
            try:
                dados_adicionais = {"distance_cm": data.get("distance_cm")} if "distance_cm" in data else None
                gerenciador_db.inserir_leitura_sensor(conn, "alerta_critico_esp32", log_cat_valor, dados_adicionais=dados_adicionais, dados_brutos=data)
                gerenciador_db.inserir_alerta_evento_sistema(conn, "ALERTA_CRITICO_RECEBIDO_ESP32", "ESP32_SENSOR", log_cat_valor, detalhes=data)
            finally:
                conn.close()
    except Exception as e: log.error(f"Processar msg status alerta crítico ESP32: {e}", exc_info=True)

def carregar_ou_recarregar_artefatos(model_p: str, scaler_p: str) -> bool:
    global ml_model_instance, scaler_instance, timestamp_artefatos_carregados
    try:
        if not os.path.exists(model_p) or not os.path.exists(scaler_p):
            log.error(f"Modelo ({os.path.basename(model_p)}) ou scaler ({os.path.basename(scaler_p)}) NÃO ENCONTRADO em '{os.path.dirname(model_p)}'.")
            ml_model_instance = None; scaler_instance = None; timestamp_artefatos_carregados = None
            return False
        ts_modelo_disco = os.path.getmtime(model_p)
        if ml_model_instance is None or scaler_instance is None or \
           timestamp_artefatos_carregados is None or \
           ts_modelo_disco > timestamp_artefatos_carregados:
            if ml_model_instance is not None: log.info(f"Nova versão do modelo. Recarregando...")
            ml_model_instance = joblib.load(model_p)
            scaler_instance = joblib.load(scaler_p)
            timestamp_artefatos_carregados = ts_modelo_disco
            log.info(f"Modelo '{os.path.basename(model_p)}' e Scaler '{os.path.basename(scaler_p)}' carregados/recarregados.")
            return True
    except Exception as e:
        log.error(f"Ao carregar/recarregar artefatos: {e}", exc_info=True)
        ml_model_instance = None; scaler_instance = None; timestamp_artefatos_carregados = None
        return False
    return True

def definir_pontos_de_interesse_para_predicao() -> pd.DataFrame:
    # ... (código da V13.7) ...
    pois_data = {
        'nome_poi': [
            'POI 1 (Praça da Alfândega - centro)', 'POI 2 (Morro Santana - leste)',
            'POI 3 (Gasômetro - próximo ao rio)', 'POI 4 (Centro de Eventos PUCRS - mais elevado)'
        ],
        'longitude': [-51.230, -51.130, -51.240, -51.180],
        'latitude': [-30.030, -30.050, -30.025, -30.058],
        'elevation': [10.0, 150.0, 5.0, 40.0],
        'distance_to_river': [100.0, 5000.0, 20.0, 1500.0],
        'slope': [9.1909, 35.0807, 0.0000, 6.7170],
        'curvature': [-0.004756, -0.004866, 0.000000, 0.002717]
    }
    return pd.DataFrame(pois_data)

def realizar_predicoes_geograficas_pois(
    pois_df_completo: pd.DataFrame, model_to_use: Any, scaler_to_use: StandardScaler,
    features_order: List[str], threshold: float
) -> List[Dict[str, Any]]:
    # ... (código da V13.7) ...
    predicoes_geo_output: List[Dict[str, Any]] = []
    if model_to_use is None or scaler_to_use is None or pois_df_completo.empty: return predicoes_geo_output
    try:
        if not all(feature in pois_df_completo.columns for feature in features_order):
            log.error(f"POIs não contêm todas as features: {features_order}"); return predicoes_geo_output
        X_pois_raw = pois_df_completo[features_order]
        X_pois_scaled = scaler_to_use.transform(X_pois_raw)
        probabilities = model_to_use.predict_proba(X_pois_scaled)[:, 1]
        for index, row in pois_df_completo.iterrows():
            prob = probabilities[index]; is_geo_high_risk = (prob >= threshold)
            predicoes_geo_output.append({
                "nome_poi": row["nome_poi"], "latitude": row["latitude"], "longitude": row["longitude"],
                "geo_probability_flood": prob, "is_geo_high_risk": is_geo_high_risk
            })
    except Exception as e: log.error(f"Predições geográficas: {e}", exc_info=True)
    return predicoes_geo_output

def carregar_camada_geografica(
    gpkg_path: str, layer_name: str, target_crs: str, layer_type_for_log: str
) -> Optional[gpd.GeoDataFrame]:
    # ... (código da V13.7) ...
    if not os.path.exists(gpkg_path):
        log.warning(f"GeoPackage '{os.path.basename(gpkg_path)}' não encontrado. Análise de impacto para {layer_type_for_log} desabilitada.")
        return None
    try:
        log.info(f"Carregando camada de {layer_type_for_log} '{layer_name}' de '{os.path.basename(gpkg_path)}'...")
        gdf = gpd.read_file(gpkg_path, layer=layer_name)
        if gdf.empty:
            log.warning(f"Camada de {layer_type_for_log} '{layer_name}' está vazia. Análise de impacto desabilitada."); return None
        gdf = gdf[gdf.geometry.is_valid & gdf.geometry.notna()]
        if gdf.empty:
            log.warning(f"Nenhuma geometria válida na camada de {layer_type_for_log} '{layer_name}'. Análise de impacto desabilitada."); return None
        if gdf.crs is None:
             log.warning(f"Camada de {layer_type_for_log} '{layer_name}' sem CRS. Assumindo {CRS_WGS84} e reprojetando para {target_crs}.")
             gdf = gdf.set_crs(CRS_WGS84, allow_override=True)
        if gdf.crs.to_string().upper() != target_crs.upper():
            log.info(f"Reprojetando {layer_type_for_log} de {gdf.crs} para {target_crs}...")
            gdf = gdf.to_crs(target_crs)
        log.info(f"{len(gdf)} feições de {layer_type_for_log} carregadas (CRS: {target_crs}).")
        if not hasattr(gdf, 'sindex') or gdf.sindex is None: 
            log.info(f"Criando índice espacial para {layer_type_for_log}...")
            gdf.sindex 
        return gdf
    except Exception as e:
        log.error(f"Falha ao carregar/processar dados de {layer_type_for_log}: {e}", exc_info=True)
        return None

def avaliar_impacto_edificacoes(
    poi_nome: str, poi_lon: float, poi_lat: float, categoria_agua_atual: Optional[str],
    original_poi_crs: str = CRS_WGS84
) -> str:
    # ... (código da V13.7) ...
    global edificios_gdf_metric
    if edificios_gdf_metric is None or edificios_gdf_metric.empty: return "Dados de edificações indisponíveis."
    raio_buffer_dinamico_meters = RAIO_BUFFER_PADRAO_METERS
    if categoria_agua_atual == "Alto": raio_buffer_dinamico_meters = RAIO_BUFFER_AGUA_ALTO_METERS
    elif categoria_agua_atual == "Medio": raio_buffer_dinamico_meters = RAIO_BUFFER_AGUA_MEDIO_METERS
    try:
        poi_geom = Point(poi_lon, poi_lat)
        poi_gdf_temp = gpd.GeoDataFrame([{'nome': poi_nome, 'geometry': poi_geom}], crs=original_poi_crs)
        poi_gdf_temp_metric = poi_gdf_temp.to_crs(edificios_gdf_metric.crs) 
        poi_buffer = poi_gdf_temp_metric.geometry.iloc[0].buffer(raio_buffer_dinamico_meters)
        if hasattr(edificios_gdf_metric, 'sindex') and edificios_gdf_metric.sindex is not None:
            possiveis_candidatos_idx = list(edificios_gdf_metric.sindex.intersection(poi_buffer.bounds))
            if not possiveis_candidatos_idx: return f"Nenhuma edificação no raio de {raio_buffer_dinamico_meters}m."
            candidatos_gdf = edificios_gdf_metric.iloc[possiveis_candidatos_idx]
            edificios_no_buffer = candidatos_gdf[candidatos_gdf.intersects(poi_buffer)]
        else:
            log.warning("Índice espacial não disponível para edificações. A consulta pode ser mais lenta.")
            edificios_no_buffer = edificios_gdf_metric[edificios_gdf_metric.intersects(poi_buffer)]
        num_afetados = len(edificios_no_buffer)
        if num_afetados == 0: return f"Nenhuma edificação no raio de {raio_buffer_dinamico_meters}m."
        type_details = []
        known_types = {
            'Hospitais': edificios_no_buffer[edificios_no_buffer['amenity'] == 'hospital'].shape[0] if 'amenity' in edificios_no_buffer.columns else 0,
            'Escolas': edificios_no_buffer[edificios_no_buffer['amenity'].isin(['school', 'kindergarten', 'college', 'university'])].shape[0] if 'amenity' in edificios_no_buffer.columns else 0,
            'Residenciais': edificios_no_buffer[edificios_no_buffer['building'].isin(['house', 'apartments', 'residential', 'detached', 'semidetached_house', 'terrace', 'bungalow', 'cabin'])].shape[0] if 'building' in edificios_no_buffer.columns else 0,
            'Comerciais/Serviços': edificios_no_buffer[
                (edificios_no_buffer['building'].isin(['commercial', 'retail', 'office']) if 'building' in edificios_no_buffer.columns else False) |
                (edificios_no_buffer['shop'].notna() if 'shop' in edificios_no_buffer.columns else False) |
                (edificios_no_buffer['office'].notna() if 'office' in edificios_no_buffer.columns else False)
            ].shape[0]
        }
        for tipo, contagem in known_types.items():
            if contagem > 0: type_details.append(f"{tipo}: {contagem}")
        tipos_str = ", ".join(type_details) if type_details else "Tipos específicos não contabilizados."
        return f"~{num_afetados} edificações (Raio: {raio_buffer_dinamico_meters}m) ({tipos_str})"
    except Exception as e:
        log.error(f"POI {poi_nome} - Erro ao calcular impacto em edificações: {e}", exc_info=True)
        return "Erro ao calcular impacto em edificações."

def avaliar_impacto_estradas(
    poi_nome: str, poi_lon: float, poi_lat: float, categoria_agua_atual: Optional[str],
    original_poi_crs: str = CRS_WGS84
) -> str:
    # ... (código da V13.7 com traduções) ...
    global estradas_gdf_metric
    if estradas_gdf_metric is None or estradas_gdf_metric.empty: return "Dados de estradas indisponíveis."
    raio_buffer_dinamico_meters = RAIO_BUFFER_PADRAO_METERS
    if categoria_agua_atual == "Alto": raio_buffer_dinamico_meters = RAIO_BUFFER_AGUA_ALTO_METERS
    elif categoria_agua_atual == "Medio": raio_buffer_dinamico_meters = RAIO_BUFFER_AGUA_MEDIO_METERS
    try:
        poi_geom = Point(poi_lon, poi_lat)
        poi_gdf_temp = gpd.GeoDataFrame([{'nome': poi_nome, 'geometry': poi_geom}], crs=original_poi_crs)
        poi_gdf_temp_metric = poi_gdf_temp.to_crs(estradas_gdf_metric.crs) 
        poi_buffer = poi_gdf_temp_metric.geometry.iloc[0].buffer(raio_buffer_dinamico_meters)
        if hasattr(estradas_gdf_metric, 'sindex') and estradas_gdf_metric.sindex is not None:
            possiveis_candidatos_idx = list(estradas_gdf_metric.sindex.intersection(poi_buffer.bounds))
            if not possiveis_candidatos_idx: return f"Nenhuma estrada no raio de {raio_buffer_dinamico_meters}m."
            candidatos_gdf = estradas_gdf_metric.iloc[possiveis_candidatos_idx]
            estradas_no_buffer = candidatos_gdf[candidatos_gdf.intersects(poi_buffer)].copy()
        else:
            log.warning("Índice espacial não disponível para estradas. A consulta pode ser mais lenta.")
            estradas_no_buffer = estradas_gdf_metric[estradas_gdf_metric.intersects(poi_buffer)].copy()
        if estradas_no_buffer.empty: return f"Nenhuma estrada no raio de {raio_buffer_dinamico_meters}m."
        total_length_km = 0
        clipped_geometries = estradas_no_buffer.geometry.intersection(poi_buffer)
        valid_clipped_geometries = clipped_geometries[~clipped_geometries.is_empty & (clipped_geometries.geom_type.isin(['LineString', 'MultiLineString']))]
        if not valid_clipped_geometries.empty:
            total_length_km = valid_clipped_geometries.length.sum() / 1000
        summary_parts = [f"~{total_length_km:.2f} km de vias"]
        traducao_highway = {
            "motorway": "Autoestrada", "trunk": "Troncal", "primary": "Primária",
            "secondary": "Secundária", "tertiary": "Terciária", "unclassified": "Não Classificada",
            "residential": "Residencial", "living_street": "Rua Lazer/Pedestre",
            "service": "Serviço", "track": "Acesso Rural/Trilha", "path": "Trilha Pedestre",
            "cycleway": "Ciclovia", "footway": "Via Pedestre"
        }
        if 'highway' in estradas_no_buffer.columns:
            tipos_vias_counts = estradas_no_buffer['highway'].value_counts()
            if not tipos_vias_counts.empty:
                tipos_traduzidos_list = []
                for tipo_osm, contagem in tipos_vias_counts.nlargest(3).items():
                    tipo_pt = traducao_highway.get(str(tipo_osm).lower(), str(tipo_osm)) 
                    tipos_traduzidos_list.append(f'{tipo_pt}({contagem})')
                if tipos_traduzidos_list:
                     summary_parts.append(f"Tipos: {', '.join(tipos_traduzidos_list)}")
        if 'name' in estradas_no_buffer.columns:
            nomes_principais = estradas_no_buffer[estradas_no_buffer['name'].notna()]['name'].unique()
            if len(nomes_principais) > 0:
                 summary_parts.append(f"Vias nomeadas: {', '.join(nomes_principais[:2])}{'...' if len(nomes_principais) > 2 else ''}")
        bridges = estradas_no_buffer[estradas_no_buffer['bridge'] == 'yes'].shape[0] if 'bridge' in estradas_no_buffer.columns else 0
        tunnels = estradas_no_buffer[estradas_no_buffer['tunnel'] == 'yes'].shape[0] if 'tunnel' in estradas_no_buffer.columns else 0
        if bridges > 0: summary_parts.append(f"{bridges} ponte(s)")
        if tunnels > 0: summary_parts.append(f"{tunnels} túnel(neis)")
        return (", ".join(summary_parts) + f" (Raio: {raio_buffer_dinamico_meters}m)")
    except Exception as e:
        log.error(f"POI {poi_nome} - Erro ao calcular impacto em estradas: {e}", exc_info=True)
        return "Erro ao calcular impacto em estradas."

def avaliar_impacto_rios(
    poi_nome: str, poi_lon: float, poi_lat: float, categoria_agua_atual: Optional[str],
    original_poi_crs: str = CRS_WGS84
) -> str:
    # ... (código da V13.7) ...
    global rios_gdf_metric
    if rios_gdf_metric is None or rios_gdf_metric.empty: return "Dados de rios indisponíveis."
    raio_buffer_dinamico_meters = RAIO_BUFFER_PADRAO_METERS
    if categoria_agua_atual == "Alto": raio_buffer_dinamico_meters = RAIO_BUFFER_AGUA_ALTO_METERS
    elif categoria_agua_atual == "Medio": raio_buffer_dinamico_meters = RAIO_BUFFER_AGUA_MEDIO_METERS
    try:
        poi_geom = Point(poi_lon, poi_lat)
        poi_gdf_temp = gpd.GeoDataFrame([{'nome': poi_nome, 'geometry': poi_geom}], crs=original_poi_crs)
        poi_gdf_temp_metric = poi_gdf_temp.to_crs(rios_gdf_metric.crs)
        poi_buffer = poi_gdf_temp_metric.geometry.iloc[0].buffer(raio_buffer_dinamico_meters)
        if hasattr(rios_gdf_metric, 'sindex') and rios_gdf_metric.sindex is not None:
            possiveis_candidatos_idx = list(rios_gdf_metric.sindex.intersection(poi_buffer.bounds))
            if not possiveis_candidatos_idx: return f"Nenhum rio/canal no raio de {raio_buffer_dinamico_meters}m."
            candidatos_gdf = rios_gdf_metric.iloc[possiveis_candidatos_idx]
            rios_no_buffer = candidatos_gdf[candidatos_gdf.intersects(poi_buffer)]
        else:
            log.warning("Índice espacial não disponível para rios. A consulta pode ser mais lenta.")
            rios_no_buffer = rios_gdf_metric[rios_gdf_metric.intersects(poi_buffer)]
        if rios_no_buffer.empty: return f"Nenhum rio/canal no raio de {raio_buffer_dinamico_meters}m."
        summary_parts = []
        nomes_rios = rios_no_buffer[rios_no_buffer['name'].notna()]['name'].unique()
        if len(nomes_rios) > 0:
            summary_parts.append(f"Trechos de: {', '.join(nomes_rios[:3])}{'...' if len(nomes_rios) > 3 else ''}")
        else:
            summary_parts.append(f"{len(rios_no_buffer)} segmento(s) de rio/canal não nomeado(s)")
        if 'intermittent' in rios_no_buffer.columns and (rios_no_buffer['intermittent'] == 'yes').any():
            summary_parts.append("Contém trecho(s) intermitente(s)")
        if 'tunnel' in rios_no_buffer.columns and (rios_no_buffer['tunnel'] == 'yes').any():
            summary_parts.append("Contém trecho(s) em túnel/galeria")
        return (", ".join(summary_parts) + f" afetado(s) (Raio: {raio_buffer_dinamico_meters}m)")
    except Exception as e:
        log.error(f"POI {poi_nome} - Erro ao calcular impacto em rios: {e}", exc_info=True)
        return "Erro ao calcular impacto em rios."

def publicar_comando_alerta(client: mqtt.Client, overall_system_risk_high: bool) -> None:
    # ... (código da V13.8) ...
    global alertas_enviados_counter
    if overall_system_risk_high:
        alertas_enviados_counter += 1
        
    payload_dict = {"system_risk": "high" if overall_system_risk_high else "normal"}
    payload_json = json.dumps(payload_dict)
    try:
        if client.is_connected():
            result = client.publish(TOPIC_COMMAND_ALERT_STATUS, payload_json)
            conn_pub = gerenciador_db.criar_conexao()
            if conn_pub:
                try:
                    gerenciador_db.inserir_alerta_evento_sistema(conn_pub, "COMANDO_RISCO_SISTEMA_ESP32", "HUB_PYTHON", "high" if overall_system_risk_high else "normal", detalhes=payload_dict)
                finally:
                    conn_pub.close()
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                log.info(f"Comando Publicado: {payload_json} -> {TOPIC_COMMAND_ALERT_STATUS}")
            else: log.error(f"Publicar comando. Código: {result.rc}")
        else: log.warning("MQTT não conectado. Comando não enviado.")
    except Exception as e: log.error(f"Exceção ao publicar comando: {e}", exc_info=True)

# --- Função Principal (main) ---
def main():
    console.print(Panel(f"Iniciando Hub MQTT FloodSentry AI (V13.8.2 - Full DB with Hub Status)", title="[bold dodger_blue1]FloodSentry AI Hub[/bold dodger_blue1]", border_style="bright_blue"))
    log.info(f"Modelo: {MODEL_FILE_NAME}, Limiar Predição: {PREDICTION_THRESHOLD}")

    gerenciador_db.inicializar_banco()

    global ml_model_instance, scaler_instance, timestamp_artefatos_carregados, last_artefatos_check_time
    global esp32_critical_alert_is_active, esp32_critical_alert_details
    global latest_rainfall_data, timestamp_last_rain_data, latest_water_level_data, timestamp_last_water_data
    global edificios_gdf_metric, estradas_gdf_metric, rios_gdf_metric

    if not carregar_ou_recarregar_artefatos(MODEL_PATH, SCALER_PATH):
        log.critical("Falha no carregamento inicial do modelo/scaler. Encerrando."); return
    last_artefatos_check_time = time.time()
    
    edificios_gdf_metric = carregar_camada_geografica(OSM_GPKG_PATH, EDIFICIOS_LAYER_NAME, CRS_PROJETADO_POA, "Edificações")
    estradas_gdf_metric = carregar_camada_geografica(OSM_GPKG_PATH, ESTRADAS_LAYER_NAME, CRS_PROJETADO_POA, "Estradas")
    rios_gdf_metric = carregar_camada_geografica(OSM_GPKG_PATH, RIOS_LAYER_NAME, CRS_PROJETADO_POA, "Rios")

    pois_para_prever = definir_pontos_de_interesse_para_predicao()

    try: client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, client_id=MQTT_CLIENT_ID)
    except TypeError: client = mqtt.Client(client_id=MQTT_CLIENT_ID)
    client.on_connect = on_connect; client.on_disconnect = on_disconnect
    client.message_callback_add(TOPIC_SENSOR_WATER_LEVEL, on_message_water_level)
    client.message_callback_add(TOPIC_SENSOR_RAINFALL, on_message_rainfall)
    client.message_callback_add(TOPIC_ESP_CRITICAL_ALERT_STATUS, on_message_esp_critical_alert_status)

    mqtt_connected_successfully = False
    for attempt in range(1, MAX_MQTT_CONNECT_ATTEMPTS + 1):
        log.info(f"Tentando conectar ao Broker MQTT: {MQTT_BROKER_HOST} (Tentativa {attempt}/{MAX_MQTT_CONNECT_ATTEMPTS})...")
        try:
            client.connect(MQTT_BROKER_HOST, MQTT_BROKER_PORT, MQTT_KEEPALIVE)
            mqtt_connected_successfully = True 
            break 
        except socket.timeout: log.warning(f"Tentativa {attempt} de conexão MQTT falhou: Timeout.")
        except ConnectionRefusedError: log.warning(f"Tentativa {attempt} de conexão MQTT falhou: Conexão recusada.")
        except Exception as e: log.critical(f"Tentativa {attempt} de conexão MQTT falhou com erro inesperado: {e}", exc_info=True)
        if attempt < MAX_MQTT_CONNECT_ATTEMPTS:
            log.info(f"Aguardando {MQTT_CONNECT_RETRY_DELAY_SECONDS}s para próxima tentativa...")
            time.sleep(MQTT_CONNECT_RETRY_DELAY_SECONDS)
        else: log.critical(f"Todas as {MAX_MQTT_CONNECT_ATTEMPTS} tentativas de conexão MQTT falharam.")
    
    if not mqtt_connected_successfully:
        log.error("Não foi possível estabelecer conexão com o Broker MQTT. O Hub não poderá operar.")
        return 

    client.loop_start()

    start_time = time.time()
    ciclos_counter = 0
    last_status_log_time = time.time()
    STATUS_LOG_INTERVAL_SECONDS = 300

    try:
        predicao_intervalo_segundos = 15
        log.info(f"Ciclo de decisão a cada {predicao_intervalo_segundos} segundos.")
        console.line()

        while True:
            ciclos_counter += 1
            current_loop_time = time.time()
            timestamp_ciclo_iso_para_db = gerenciador_db.get_utc_timestamp_iso()
            
            panel_title = Text(f"Ciclo de Decisão ({time.strftime('%H:%M:%S')})", style="bold bright_blue")
            console.print(Panel("Avaliando condições...", title=panel_title, border_style="dim blue", padding=(1,2)))

            if (current_loop_time - last_artefatos_check_time) > MODEL_CHECK_INTERVAL_SECONDS:
                log.debug("Verificando por atualizações nos arquivos do modelo/scaler...")
                carregar_ou_recarregar_artefatos(MODEL_PATH, SCALER_PATH)
                last_artefatos_check_time = current_loop_time
            if ml_model_instance is None or scaler_instance is None:
                log.error("Modelo ou scaler não carregado. Pulando ciclo."); time.sleep(predicao_intervalo_segundos); continue

            sistema_em_alto_risco_final = False
            
            sensor_table = Table(title="[bold dodger_blue1]Status dos Sensores[/bold dodger_blue1]", show_header=True, header_style="bold magenta", border_style="dim cyan", box=box.ROUNDED)
            sensor_table.add_column("Sensor", style="cyan", width=15)
            sensor_table.add_column("Status Atual", style="white", width=20)
            sensor_table.add_column("Categoria Recebida", style="white", width=20)

            status_sensor_agua_obj = Text("N/A"); categoria_agua_display = "N/A"; dados_agua_atuais = False
            if latest_water_level_data and timestamp_last_water_data:
                categoria_agua_display = latest_water_level_data.get('level_category', 'N/A')
                if (current_loop_time - timestamp_last_water_data) < SENSOR_DATA_TIMEOUT_SECONDS:
                    dados_agua_atuais = True; status_sensor_agua_obj = Text("Atual", style="green")
                else: status_sensor_agua_obj = Text("Desatualizado", style="orange3")
            elif timestamp_last_water_data is None : status_sensor_agua_obj = Text("Sem Comunicação", style="red")
            cat_agua_style = "green" if categoria_agua_display == "Baixo" else "yellow" if categoria_agua_display == "Medio" else "red" if categoria_agua_display == "Alto" else "white"
            sensor_table.add_row("Nível Água", status_sensor_agua_obj, Text(categoria_agua_display, style=cat_agua_style))

            status_sensor_chuva_obj = Text("N/A"); categoria_chuva_display = "N/A"; dados_chuva_atuais = False
            if latest_rainfall_data and timestamp_last_rain_data:
                categoria_chuva_display = latest_rainfall_data.get('intensity_category', 'N/A')
                if (current_loop_time - timestamp_last_rain_data) < SENSOR_DATA_TIMEOUT_SECONDS:
                    dados_chuva_atuais = True; status_sensor_chuva_obj = Text("Atual", style="green")
                else: status_sensor_chuva_obj = Text("Desatualizado", style="orange3")
            elif timestamp_last_rain_data is None : status_sensor_chuva_obj = Text("Sem Comunicação", style="red")
            cat_chuva_style = "green" if categoria_chuva_display in ["Nenhuma", "Leve"] else "yellow" if categoria_chuva_display == "Moderada" else "red" if categoria_chuva_display == "Pesada" else "white"
            sensor_table.add_row("Qtd. Chuva", status_sensor_chuva_obj, Text(categoria_chuva_display, style=cat_chuva_style))
            console.print(sensor_table)

            if esp32_critical_alert_is_active:
                dist = esp32_critical_alert_details.get('distance_cm','N/A') if esp32_critical_alert_details else 'N/A'
                console.print(Panel(Text(f"Distância do Sensor: {dist} cm", style="bold red"), title="[bold red]ALERTA CRÍTICO PRIORITÁRIO (ESP32)[/bold red]", border_style="red", expand=False))
                sistema_em_alto_risco_final = True
                if dados_chuva_atuais and categoria_chuva_display not in ["Nenhuma", "N/A"]:
                    log.info("Alerta crítico ESP32 ativo. Detalhando POIs devido à chuva para análise de impacto...")
                else:
                    log.info("Alerta crítico ESP32 ativo. (Chuva não significativa/ausente para análise de impacto detalhada dos POIs)")

            mostrar_analise_detalhada_pois = False; mensagem_pois_simplificada = ""
            if not sistema_em_alto_risco_final:
                cat_agua_plain_status_main = categoria_agua_display if dados_agua_atuais else (status_sensor_agua_obj.plain if isinstance(status_sensor_agua_obj, Text) else str(status_sensor_agua_obj))
                cat_chuva_plain_status_main = categoria_chuva_display if dados_chuva_atuais else (status_sensor_chuva_obj.plain if isinstance(status_sensor_chuva_obj, Text) else str(status_sensor_chuva_obj))

                if not dados_chuva_atuais :
                    mensagem_pois_simplificada = f"Sensor de Qtd. Chuva: {cat_chuva_plain_status_main}. Análise detalhada suspensa."
                elif categoria_chuva_display == "Nenhuma":
                    mensagem_pois_simplificada = f"Qtd. Chuva: Nenhuma. Nível d'Água: {cat_agua_plain_status_main}."
                elif categoria_chuva_display in ["Leve", "Moderada", "Pesada"]:
                    mostrar_analise_detalhada_pois = True
                else: 
                     mensagem_pois_simplificada = f"Qtd. Chuva: {cat_chuva_plain_status_main} (estado incerto). Análise detalhada suspensa."
            elif esp32_critical_alert_is_active and (not dados_chuva_atuais or categoria_chuva_display in ["Nenhuma", "N/A"]): pass
            elif esp32_critical_alert_is_active: mostrar_analise_detalhada_pois = True
            
            poi_table = Table(title="[bold dodger_blue1]Análise dos Pontos de Interesse (POIs)[/bold dodger_blue1]",
                              show_header=True, header_style="bold cyan",
                              border_style="dim blue", box=box.ROUNDED, show_lines=True)
            poi_table.add_column("Nome POI", style="white bold", width=35, overflow="fold")
            poi_table.add_column("Risco Geo.", style="white", width=10) 
            poi_table.add_column("Prob. Geo.", style="magenta", width=12, justify="right")
            poi_table.add_column("Status Combinado / Sensores", style="white", width=50, overflow="fold") 
            poi_table.add_column("Impacto Estimado (Edif./Infra.)", style="white", width=60, overflow="fold")

            if mostrar_analise_detalhada_pois and not pois_para_prever.empty:
                if not sistema_em_alto_risco_final: log.info(f"Qtd. Chuva: {categoria_chuva_display}. Realizando análise detalhada dos POIs...")
                predicoes_geograficas = realizar_predicoes_geograficas_pois(
                    pois_para_prever, ml_model_instance, scaler_instance, FEATURES_ORDER, PREDICTION_THRESHOLD
                )
                algum_poi_em_alerta_combinado = False
                conn_analise = gerenciador_db.criar_conexao()

                for p_geo in predicoes_geograficas:
                    nome_poi = p_geo["nome_poi"]; risco_geo_alto = p_geo["is_geo_high_risk"]; prob_geo = p_geo["geo_probability_flood"]
                    lat_poi, lon_poi = p_geo["latitude"], p_geo["longitude"]
                    status_final_poi_text = Text(""); prob_geo_percent_str = f"{prob_geo*100:.1f}%"
                    risco_geo_text = Text("Alto", style="red bold") if risco_geo_alto else Text("Baixo", style="green")
                    
                    full_impact_text_obj = Text("")
                    info_edificacoes_db = "---"; info_estradas_db = "---"; info_rios_db = "---"
                    raio_buffer_usado_db = RAIO_BUFFER_PADRAO_METERS
                    
                    cat_agua_plain_status_poi = status_sensor_agua_obj.plain if isinstance(status_sensor_agua_obj, Text) else str(status_sensor_agua_obj)
                    if not dados_agua_atuais:
                        status_final_poi_text.append(f"Sensor Água: {cat_agua_plain_status_poi} (Qtd. Chuva: {categoria_chuva_display})")
                        full_impact_text_obj.append("--- (Análise de impacto suspensa devido a dados de água)")
                    else:
                        agua_alerta = categoria_agua_display in ["Medio", "Alto"]
                        chuva_para_alerta_combinado = categoria_chuva_display in ["Moderada", "Pesada"]
                        sensores_em_alerta_combinado = agua_alerta or chuva_para_alerta_combinado

                        if risco_geo_alto and sensores_em_alerta_combinado:
                            status_final_poi_text.append("ALTO RISCO", style="red bold")
                            status_final_poi_text.append(f" (Sensores [Água: {categoria_agua_display}, Qtd. Chuva: {categoria_chuva_display}])")
                            algum_poi_em_alerta_combinado = True
                            
                            info_edificacoes_db = avaliar_impacto_edificacoes(nome_poi, lon_poi, lat_poi, categoria_agua_display)
                            edif_text = Text(info_edificacoes_db)
                            if info_edificacoes_db not in ["---", "Dados de edificações indisponíveis."] and not info_edificacoes_db.startswith("Nenhuma edificação"):
                                edif_text.stylize("red")
                            full_impact_text_obj.append("Edif: ", style="bold default")
                            full_impact_text_obj.append(edif_text)

                            info_estradas_db = avaliar_impacto_estradas(nome_poi, lon_poi, lat_poi, categoria_agua_display)
                            if info_estradas_db and not info_estradas_db.startswith("Dados de estradas indisponíveis"):
                                full_impact_text_obj.append("\nEstr: ", style="bold default")
                                estrada_text = Text(info_estradas_db)
                                if not info_estradas_db.startswith("Nenhuma estrada") and not info_estradas_db.startswith("Erro ao calcular"):
                                     estrada_text.stylize("red")
                                full_impact_text_obj.append(estrada_text)
                            
                            info_rios_db = avaliar_impacto_rios(nome_poi, lon_poi, lat_poi, categoria_agua_display)
                            if info_rios_db and not info_rios_db.startswith("Dados de rios indisponíveis"):
                                full_impact_text_obj.append("\nRios: ", style="bold default")
                                rio_text = Text(info_rios_db)
                                if not info_rios_db.startswith("Nenhum rio") and not info_rios_db.startswith("Erro ao calcular"):
                                    rio_text.stylize("red")
                                full_impact_text_obj.append(rio_text)
                            
                            if categoria_agua_display == "Alto": raio_buffer_usado_db = RAIO_BUFFER_AGUA_ALTO_METERS
                            elif categoria_agua_display == "Medio": raio_buffer_usado_db = RAIO_BUFFER_AGUA_MEDIO_METERS
                        else: 
                            sensores_str = f"Sensores [Água: {categoria_agua_display}, Qtd. Chuva: {categoria_chuva_display}]"
                            if risco_geo_alto and not sensores_em_alerta_combinado:
                                status_final_poi_text.append("Risco Geo. ALTO, Condições Atuais OK", style="orange3")
                                status_final_poi_text.append(f" ({sensores_str})")
                            else:
                                status_final_poi_text.append("BAIXO RISCO", style="green")
                                status_final_poi_text.append(f" ({sensores_str})")
                            full_impact_text_obj.append("--- (Sem alto risco combinado)")
                    
                    poi_table.add_row(nome_poi, risco_geo_text, prob_geo_percent_str, status_final_poi_text, full_impact_text_obj)
                    
                    if conn_analise:
                        gerenciador_db.inserir_analise_poi(conn_analise, {
                            "timestamp_ciclo_iso": timestamp_ciclo_iso_para_db, "nome_poi": nome_poi,
                            "latitude_poi": lat_poi, "longitude_poi": lon_poi, "prob_geo_inundacao": prob_geo,
                            "risco_geo_alto_bool": risco_geo_alto, "categoria_agua_sensor_no_ciclo": categoria_agua_display,
                            "categoria_chuva_sensor_no_ciclo": categoria_chuva_display, "status_combinado_poi": status_final_poi_text.plain,
                            "raio_buffer_impacto_m": raio_buffer_usado_db, "impacto_edificacoes_txt": info_edificacoes_db,
                            "impacto_estradas_txt": info_estradas_db, "impacto_rios_txt": info_rios_db
                        })

                if conn_analise: conn_analise.close()
                if algum_poi_em_alerta_combinado and not sistema_em_alto_risco_final: sistema_em_alto_risco_final = True
                console.print(poi_table)

            elif not pois_para_prever.empty:
                for index, poi_info in pois_para_prever.iterrows():
                    poi_table.add_row(poi_info['nome_poi'], Text("---", style="dim white"), Text("---", style="dim white"), Text(mensagem_pois_simplificada, overflow="fold", style="dim white"), Text("---", style="dim white"))
                if not poi_table.rows: log.info("Nenhuma análise detalhada dos POIs solicitada ou aplicável neste ciclo.")
                else: console.print(poi_table)
            elif pois_para_prever.empty : log.info("Nenhum POI para analisar.")

            decisao_final_style = Style(color="red", bold=True) if sistema_em_alto_risco_final else Style(color="green")
            console.print(Panel(Text(f"Sistema em Risco Alto = {sistema_em_alto_risco_final}", style=decisao_final_style),
                                title="[bold dodger_blue1]Decisão Final do Ciclo[/bold dodger_blue1]", border_style="bright_blue", expand=False))
            publicar_comando_alerta(client, sistema_em_alto_risco_final)
            console.line(2)
            
            if (current_loop_time - last_status_log_time) > STATUS_LOG_INTERVAL_SECONDS:
                uptime = current_loop_time - start_time
                conn_status = gerenciador_db.criar_conexao()
                if conn_status:
                    try:
                        gerenciador_db.inserir_status_hub(
                            conn_status, uptime, ciclos_counter,
                            msgs_recebidas_counter, alertas_enviados_counter
                        )
                        log.info("Status do Hub salvo no banco de dados.")
                    finally:
                        conn_status.close()
                last_status_log_time = current_loop_time

            time.sleep(predicao_intervalo_segundos)
    except KeyboardInterrupt: log.info("\nInterrupção pelo usuário. Encerrando...")
    except Exception as e:
        log.critical("ERRO INESPERADO no loop principal:", exc_info=True)
    finally:
        log.info("Parando loop MQTT e desconectando..."); client.loop_stop(); client.disconnect()
        log.info("Hub MQTT FloodSentry AI encerrado.")
        console.print(Panel("[bold red]FloodSentry AI Hub Encerrado[/bold red]", border_style="red"))

if __name__ == "__main__":
    main()