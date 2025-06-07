# treinar_modelo.py
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
import joblib
import os
import sys
from typing import Optional, Tuple, List, Dict, Any
import traceback
import gerenciador_db
import json

# --- Constantes de Configuração ---
# Caminhos atualizados para a nova estrutura de pastas
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
OUTPUT_MODEL_DIR = os.path.join(ROOT_DIR, 'output', 'model')

MODEL_OUTPUT_FILE_NAME: str = "modelo_xgb_slope_curvature_scaled.pkl" 
SCALER_OUTPUT_FILE_NAME: str = "scaler_slope_curvature_features.pkl"
MODEL_OUTPUT_PATH: str = os.path.join(OUTPUT_MODEL_DIR, MODEL_OUTPUT_FILE_NAME)
SCALER_OUTPUT_PATH: str = os.path.join(OUTPUT_MODEL_DIR, SCALER_OUTPUT_FILE_NAME)

FEATURES_COLUMNS: list[str] = ['longitude', 'latitude', 'elevation', 'distance_to_river', 'slope', 'curvature'] 
TARGET_COLUMN: str = 'is_flooded'
TEST_SET_SIZE: float = 0.3 
RANDOM_STATE_SEED: int = 42 
CUSTOM_CLASSIFICATION_THRESHOLD: float = 0.028

XGB_PARAMS: Dict[str, Any] = {
    'n_estimators': 200, 'learning_rate': 0.1, 'max_depth': 5,
    'subsample': 0.8, 'colsample_bytree': 0.8, 'objective': 'binary:logistic',
    'eval_metric': 'logloss', 'random_state': RANDOM_STATE_SEED, 'n_jobs': -1
}

def carregar_dados_do_banco() -> Optional[pd.DataFrame]:
    """Carrega os dados de treinamento diretamente do banco de dados SQLite."""
    print("\nCarregando dados de treinamento do banco de dados...")
    conn = gerenciador_db.criar_conexao()
    if not conn:
        print("ERRO FATAL: Não foi possível conectar ao banco de dados.")
        return None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='DadosTreinamento'")
        if cursor.fetchone() is None:
            print("ERRO FATAL: A tabela 'DadosTreinamento' não existe no banco. Execute 'preparar_dados_treinamento.py' primeiro.")
            return None

        df = pd.read_sql_query("SELECT * FROM DadosTreinamento", conn)
        print(f"Dataset carregado do banco. Linhas: {len(df)}, Colunas: {len(df.columns)}.")
        if df.empty:
            print(f"AVISO: Tabela 'DadosTreinamento' está vazia.")
            return None
        return df
    except Exception as e:
        print(f"ERRO FATAL: Ao carregar dados do banco. Causa: {e}")
        return None
    finally:
        if conn:
            conn.close()

def preparar_features_alvo(
    data: pd.DataFrame, feature_cols: list[str], target_col: str
) -> Optional[Tuple[pd.DataFrame, pd.Series]]:
    try:
        X = data[feature_cols]
        y = data[target_col]
        print(f"\nFeatures (X) selecionadas: {feature_cols}")
        print(f"Variável alvo (y) selecionada: {target_col}")
        print(f"Formato de X: {X.shape}, Formato de y: {y.shape}")
        print("\nContagem de classes na variável alvo (y) antes da divisão:")
        print(y.value_counts(normalize=True)) 
        return X, y
    except KeyError as e:
        print(f"ERRO FATAL: Coluna não encontrada. Esperadas X: {feature_cols}, y: {target_col}. Erro: {e}")
        return None 

def treinar_modelo_xgboost(
    X_train: pd.DataFrame, y_train: pd.Series,
    params: Dict[str, Any]
) -> Optional[XGBClassifier]:
    count_negative = y_train.value_counts().get(0, 0)
    count_positive = y_train.value_counts().get(1, 0)
    
    if count_positive == 0:
        print("AVISO: Nenhuma instância positiva encontrada nos dados de treinamento para XGBoost.")
        scale_pos_weight = 1
    else:
        scale_pos_weight = count_negative / count_positive
        print(f"INFO (XGBoost): Calculado scale_pos_weight: {scale_pos_weight:.2f}")

    params_com_scale = params.copy()
    params_com_scale['scale_pos_weight'] = scale_pos_weight
    
    model = XGBClassifier(**params_com_scale)
    
    print(f"\nTreinando XGBClassifier...")
    try:
        model.fit(X_train, y_train)
        print("Modelo XGBoost treinado com sucesso.")
        return model
    except Exception as e:
        print(f"ERRO FATAL: Falha no treinamento do XGBoost. Causa: {e}")
        traceback.print_exc()
        return None 

def avaliar_e_salvar_metricas(
    model: XGBClassifier, X_test: pd.DataFrame, y_test: pd.Series,
    threshold: float, params: dict
) -> None:
    y_pred_proba = model.predict_proba(X_test)[:, 1] 
    y_pred_custom_threshold = (y_pred_proba >= threshold).astype(int)
    print(f"\n--- Avaliação do Modelo XGBoost (limiar = {threshold}) ---")
    accuracy_custom = accuracy_score(y_test, y_pred_custom_threshold)
    print(f"Acurácia: {accuracy_custom:.4f}")
    
    report_dict = classification_report(y_test, y_pred_custom_threshold,
                                        target_names=['Não Inundado (0)', 'Inundado (1)'],
                                        zero_division=0, output_dict=True)
    print("\nRelatório de Classificação Detalhado:")
    print(classification_report(y_test, y_pred_custom_threshold,
                                target_names=['Não Inundado (0)', 'Inundado (1)'], zero_division=0))
    
    cm = confusion_matrix(y_test, y_pred_custom_threshold)
    print("\nMatriz de Confusão:"); print(cm)
    
    try:
        vn, fp, fn, vp = cm.ravel()
    except ValueError:
        vn, fp, fn, vp = (cm[0,0], 0, 0, 0) if y_test.unique()[0] == 0 else (0, 0, 0, cm[0,0])

    print(f"  Verdadeiros Negativos (VN): {vn}")
    print(f"  Falsos Positivos (FP): {fp}")
    print(f"  Falsos Negativos (FN): {fn}")
    print(f"  Verdadeiros Positivos (VP): {vp}")

    metricas_para_db = {
        "acuracia": accuracy_custom,
        "relatorio_classificacao": report_dict,
        "matriz_confusao": {"VN": int(vn), "FP": int(fp), "FN": int(fn), "VP": int(vp)}
    }
    
    conn = gerenciador_db.criar_conexao()
    if conn:
        try:
            gerenciador_db.inserir_metricas_treinamento(
                conn,
                MODEL_OUTPUT_FILE_NAME,
                SCALER_OUTPUT_FILE_NAME,
                params,
                threshold,
                metricas_para_db
            )
        finally:
            conn.close()

def salvar_artefatos(obj_to_save: any, output_path: str, description: str) -> bool:
    try:
        # Garante que o diretório de saída exista
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        joblib.dump(obj_to_save, output_path)
        print(f"\nINFO: {description} salvo com sucesso em: {output_path}")
        return True
    except Exception as e:
        print(f"ERRO FATAL: Salvar {description} em '{output_path}'. Causa: {e}")
        return False

def main():
    print("Iniciando script de treinamento (Fonte: DB, Saída de Métricas: DB)...")
    gerenciador_db.inicializar_banco()
    
    dados = carregar_dados_do_banco()
    if dados is None: return 
    
    prep_result = preparar_features_alvo(dados, FEATURES_COLUMNS, TARGET_COLUMN)
    if prep_result is None: return
    X, y = prep_result

    if X.empty or y.empty: print("ERRO FATAL: Features (X) ou alvo (y) vazios."); return

    print(f"\nDividindo dados em treinamento ({1-TEST_SET_SIZE:.0%}) e teste ({TEST_SET_SIZE:.0%})...")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SET_SIZE, random_state=RANDOM_STATE_SEED, stratify=y
    )
    print(f"X_train: {X_train.shape}, X_test: {X_test.shape}, y_train: {y_train.shape}, y_test: {y_test.shape}")

    print("\nAplicando Feature Scaling (StandardScaler)...")
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train) 
    X_test_scaled = scaler.transform(X_test)       
    print("Feature Scaling aplicado.")

    modelo = treinar_modelo_xgboost(
        X_train_scaled, y_train,
        params=XGB_PARAMS
    )
    if modelo is None: return

    avaliar_e_salvar_metricas(modelo, X_test_scaled, y_test, CUSTOM_CLASSIFICATION_THRESHOLD, XGB_PARAMS)
    
    model_saved = salvar_artefatos(modelo, MODEL_OUTPUT_PATH, "Modelo XGBoost")
    scaler_saved = salvar_artefatos(scaler, SCALER_OUTPUT_PATH, "Scaler")

    if model_saved and scaler_saved:
        print("\nProcesso de treinamento, avaliação e salvamento concluído.")
    else:
        print("\nProcesso de treinamento concluído, MAS FALHA AO SALVAR ARTEFATOS.")

if __name__ == "__main__":
    main()