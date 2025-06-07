# gerenciador_db.py
import sqlite3
from sqlite3 import Error
import logging
from datetime import datetime, timezone
import json
from typing import Optional, List
import os
import pandas as pd

log_db = logging.getLogger("rich")

# --- CAMINHO DO BANCO DE DADOS CORRIGIDO ---
# Navega dois níveis para cima (de src/python para a raiz) e depois entra em output/database
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DB_FILE = os.path.join(ROOT_DIR, 'output', 'database', 'floodsentry_data.db')
# --- FIM DA CORREÇÃO ---


# --- DEFINIÇÕES SQL COMPLETAS ---
SQL_CREATE_LEITURAS_SENSORES = """
CREATE TABLE IF NOT EXISTS LeiturasSensores (
    id_leitura INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_iso TEXT NOT NULL,
    tipo_sensor TEXT NOT NULL,
    categoria_valor TEXT,
    dados_adicionais_json TEXT,
    dados_brutos_json TEXT
);
"""
SQL_CREATE_ANALISES_POIS = """
CREATE TABLE IF NOT EXISTS AnalisesPOIs (
    id_analise_poi INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_ciclo_iso TEXT NOT NULL,
    nome_poi TEXT NOT NULL,
    latitude_poi REAL,
    longitude_poi REAL,
    prob_geo_inundacao REAL,
    risco_geo_alto_bool INTEGER,
    categoria_agua_sensor_no_ciclo TEXT,
    categoria_chuva_sensor_no_ciclo TEXT,
    status_combinado_poi TEXT,
    raio_buffer_impacto_m INTEGER,
    impacto_edificacoes_txt TEXT,
    impacto_estradas_txt TEXT,
    impacto_rios_txt TEXT
);
"""
SQL_CREATE_ALERTAS_EVENTOS_SISTEMA = """
CREATE TABLE IF NOT EXISTS AlertasEventosSistema (
    id_alerta_evento INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_iso TEXT NOT NULL,
    tipo_evento TEXT NOT NULL,
    origem_evento TEXT,
    nivel_ou_status_evento TEXT,
    detalhes_json TEXT
);
"""
SQL_CREATE_DADOS_TREINAMENTO = """
CREATE TABLE IF NOT EXISTS DadosTreinamento (
    id_dado INTEGER PRIMARY KEY AUTOINCREMENT,
    longitude REAL NOT NULL,
    latitude REAL NOT NULL,
    elevation REAL,
    distance_to_river REAL,
    slope REAL,
    curvature REAL,
    is_flooded INTEGER NOT NULL
);
"""
SQL_CREATE_METRICAS_TREINAMENTO = """
CREATE TABLE IF NOT EXISTS MetricasTreinamento (
    id_treinamento INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_treinamento_iso TEXT NOT NULL,
    nome_modelo_salvo TEXT,
    nome_scaler_salvo TEXT,
    parametros_json TEXT,
    limiar_classificacao REAL,
    metricas_json TEXT
);
"""
SQL_CREATE_STATUS_HUB = """
CREATE TABLE IF NOT EXISTS StatusHub (
    id_status INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp_status_iso TEXT NOT NULL,
    uptime_segundos REAL,
    ciclos_decisao_executados INTEGER,
    mensagens_mqtt_recebidas INTEGER,
    alertas_sistema_enviados INTEGER
);
"""
SQL_CREATE_PONTOS_DE_INTERESSE = """
CREATE TABLE IF NOT EXISTS PontosDeInteresse (
    nome_poi TEXT PRIMARY KEY,
    longitude_original REAL,
    latitude_original REAL,
    slope_degrees REAL,
    curvature_laplacian REAL,
    timestamp_ultima_atualizacao TEXT
);
"""

def criar_conexao(db_file=DB_FILE):
    """Cria uma conexão com o banco de dados SQLite."""
    conn = None
    try:
        # Garante que o diretório do banco de dados exista
        os.makedirs(os.path.dirname(db_file), exist_ok=True)
        conn = sqlite3.connect(db_file)
    except Error as e:
        log_db.error(f"Erro ao conectar ao banco de dados '{db_file}': {e}", exc_info=True)
    return conn

def criar_tabela(conn, sql_create_table):
    """Cria uma tabela usando a instrução SQL fornecida."""
    try:
        c = conn.cursor()
        c.execute(sql_create_table)
    except Error as e:
        log_db.error(f"Erro ao criar tabela: {e}", exc_info=True)

def inicializar_banco():
    """Cria o arquivo do banco de dados e todas as tabelas, se não existirem."""
    log_db.info(f"Inicializando e verificando todas as tabelas no banco de dados: {DB_FILE}...")
    conn = criar_conexao()
    if conn is not None:
        try:
            criar_tabela(conn, SQL_CREATE_LEITURAS_SENSORES)
            criar_tabela(conn, SQL_CREATE_ANALISES_POIS)
            criar_tabela(conn, SQL_CREATE_ALERTAS_EVENTOS_SISTEMA)
            criar_tabela(conn, SQL_CREATE_DADOS_TREINAMENTO)
            criar_tabela(conn, SQL_CREATE_METRICAS_TREINAMENTO)
            criar_tabela(conn, SQL_CREATE_STATUS_HUB)
            criar_tabela(conn, SQL_CREATE_PONTOS_DE_INTERESSE)
        finally:
            conn.close()
        log_db.info("Verificação de tabelas do banco de dados concluída.")
    else:
        log_db.error("Não foi possível criar a conexão com o banco de dados para inicialização.")

def get_utc_timestamp_iso():
    """Retorna o timestamp atual em UTC no formato ISO 8601."""
    return datetime.now(timezone.utc).isoformat()

def inserir_leitura_sensor(conn, tipo_sensor: str, categoria_valor: str, dados_adicionais: Optional[dict] = None, dados_brutos: Optional[dict] = None):
    # (Função sem alterações)
    sql = ''' INSERT INTO LeiturasSensores(timestamp_iso, tipo_sensor, categoria_valor, dados_adicionais_json, dados_brutos_json) VALUES(?,?,?,?,?) '''
    cur = conn.cursor()
    timestamp = get_utc_timestamp_iso()
    dados_adicionais_str = json.dumps(dados_adicionais) if dados_adicionais else None
    dados_brutos_str = json.dumps(dados_brutos) if dados_brutos else None
    try:
        cur.execute(sql, (timestamp, tipo_sensor, categoria_valor, dados_adicionais_str, dados_brutos_str))
        conn.commit()
        return cur.lastrowid
    except Error as e:
        log_db.error(f"Erro ao inserir leitura do sensor '{tipo_sensor}': {e}", exc_info=True)
        return None

def inserir_analise_poi(conn, dados_analise: dict):
    # (Função sem alterações)
    sql = ''' INSERT INTO AnalisesPOIs(timestamp_ciclo_iso, nome_poi, latitude_poi, longitude_poi, prob_geo_inundacao, risco_geo_alto_bool, categoria_agua_sensor_no_ciclo, categoria_chuva_sensor_no_ciclo, status_combinado_poi, raio_buffer_impacto_m, impacto_edificacoes_txt, impacto_estradas_txt, impacto_rios_txt) VALUES(:timestamp_ciclo_iso, :nome_poi, :latitude_poi, :longitude_poi, :prob_geo_inundacao, :risco_geo_alto_bool, :categoria_agua_sensor_no_ciclo, :categoria_chuva_sensor_no_ciclo, :status_combinado_poi, :raio_buffer_impacto_m, :impacto_edificacoes_txt, :impacto_estradas_txt, :impacto_rios_txt) '''
    cur = conn.cursor()
    try:
        cur.execute(sql, dados_analise)
        conn.commit()
        return cur.lastrowid
    except Error as e:
        log_db.error(f"Erro ao inserir análise do POI '{dados_analise.get('nome_poi')}': {e}", exc_info=True)
        return None

def inserir_alerta_evento_sistema(conn, tipo_evento: str, origem_evento: str, nivel_ou_status_evento: str, detalhes: Optional[dict] = None):
    # (Função sem alterações)
    sql = ''' INSERT INTO AlertasEventosSistema(timestamp_iso, tipo_evento, origem_evento, nivel_ou_status_evento, detalhes_json) VALUES(?,?,?,?,?) '''
    cur = conn.cursor()
    timestamp = get_utc_timestamp_iso()
    detalhes_str = json.dumps(detalhes) if detalhes else None
    try:
        cur.execute(sql, (timestamp, tipo_evento, origem_evento, nivel_ou_status_evento, detalhes_str))
        conn.commit()
        return cur.lastrowid
    except Error as e:
        log_db.error(f"Erro ao inserir alerta/evento '{tipo_evento}': {e}", exc_info=True)
        return None

def inserir_dados_treinamento_em_lote(conn, dataframe: pd.DataFrame):
    """Apaga os dados antigos e insere um DataFrame na tabela DadosTreinamento."""
    try:
        log_db.info(f"Apagando dados antigos da tabela 'DadosTreinamento'...")
        conn.execute("DELETE FROM DadosTreinamento")
        log_db.info(f"Inserindo {len(dataframe)} novos registros de treinamento no banco de dados...")
        dataframe.to_sql("DadosTreinamento", conn, if_exists="append", index=False)
        conn.commit()
        log_db.info("Dados de treinamento inseridos com sucesso.")
    except Exception as e:
        log_db.error(f"Falha ao inserir dados de treinamento em lote: {e}", exc_info=True)
        conn.rollback()

def inserir_metricas_treinamento(conn, nome_modelo: str, nome_scaler: str, parametros: dict, limiar: float, metricas: dict):
    """Insere as métricas de uma execução de treinamento."""
    sql = ''' INSERT INTO MetricasTreinamento(timestamp_treinamento_iso, nome_modelo_salvo, nome_scaler_salvo, parametros_json, limiar_classificacao, metricas_json)
              VALUES(?,?,?,?,?,?) '''
    cur = conn.cursor()
    timestamp = get_utc_timestamp_iso()
    parametros_str = json.dumps(parametros)
    metricas_str = json.dumps(metricas)
    try:
        cur.execute(sql, (timestamp, nome_modelo, nome_scaler, parametros_str, limiar, metricas_str))
        conn.commit()
        log_db.info(f"Métricas do treinamento do modelo '{nome_modelo}' salvas no banco de dados.")
    except Error as e:
        log_db.error(f"Erro ao inserir métricas de treinamento: {e}", exc_info=True)

def inserir_status_hub(conn, uptime_s: float, ciclos: int, msgs: int, alertas: int):
    """Insere um snapshot do status do hub."""
    sql = ''' INSERT INTO StatusHub(timestamp_status_iso, uptime_segundos, ciclos_decisao_executados, mensagens_mqtt_recebidas, alertas_sistema_enviados)
              VALUES(?,?,?,?,?) '''
    cur = conn.cursor()
    timestamp = get_utc_timestamp_iso()
    try:
        cur.execute(sql, (timestamp, uptime_s, ciclos, msgs, alertas))
        conn.commit()
    except Error as e:
        log_db.error(f"Erro ao inserir status do hub: {e}", exc_info=True)

def atualizar_features_pois(conn, dataframe: pd.DataFrame):
    """Insere ou atualiza as features de um POI na tabela PontosDeInteresse."""
    sql_upsert = """
    INSERT INTO PontosDeInteresse (nome_poi, longitude_original, latitude_original, slope_degrees, curvature_laplacian, timestamp_ultima_atualizacao)
    VALUES (?, ?, ?, ?, ?, ?)
    ON CONFLICT(nome_poi) DO UPDATE SET
        longitude_original = excluded.longitude_original,
        latitude_original = excluded.latitude_original,
        slope_degrees = excluded.slope_degrees,
        curvature_laplacian = excluded.curvature_laplacian,
        timestamp_ultima_atualizacao = excluded.timestamp_ultima_atualizacao;
    """
    cur = conn.cursor()
    timestamp = get_utc_timestamp_iso()
    try:
        for index, row in dataframe.iterrows():
            cur.execute(sql_upsert, (
                row['nome_poi'], row['longitude_original'], row['latitude_original'],
                row['slope_degrees'], row['curvature_laplacian'], timestamp
            ))
        conn.commit()
        log_db.info(f"{len(dataframe)} POIs inseridos/atualizados no banco de dados.")
    except Error as e:
        log_db.error(f"Erro ao inserir/atualizar features de POIs: {e}", exc_info=True)