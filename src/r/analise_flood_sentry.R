# analise_flood_sentry.R (Versão Final Corrigida)

# --- ETAPA 0: DEFINIR DIRETÓRIO DE TRABALHO ---
# Garante que o R procurará os arquivos na pasta raiz do projeto.
tryCatch({
  setwd("C:/Users/Golden/Documents/FIAP/fiap-1TIAOB-2025/grupo-GT08/Fase_4/Global_Solution")
  print(paste("Diretório de trabalho definido para:", getwd()))
}, error = function(e) {
  stop("ERRO: O caminho definido em setwd() não foi encontrado. Verifique se o caminho está correto.")
})


# --- ETAPA 1: INSTALAR E CARREGAR PACOTES ---
packages <- c("RSQLite", "DBI", "dplyr", "ggplot2", "sf", "lubridate", "jsonlite", "tidyr", "forcats", "rosm", "purrr")
new.packages <- packages[!(packages %in% installed.packages()[,"Package"])]
if(length(new.packages)) install.packages(new.packages)

lapply(packages, library, character.only = TRUE)


# --- ETAPA 2: CONECTAR E CARREGAR DADOS ---
db_path <- file.path("output", "database", "floodsentry_data.db")
if (!file.exists(db_path)) {
  stop("Arquivo do banco de dados '", db_path, "' não encontrado no diretório de trabalho. Execute os scripts Python primeiro.")
}
con <- dbConnect(RSQLite::SQLite(), db_path)

# Usando dbReadTable para uma leitura mais direta
leituras_sensores_df <- dbReadTable(con, "LeiturasSensores")
analises_pois_df <- dbReadTable(con, "AnalisesPOIs")
metricas_treinamento_df <- dbReadTable(con, "MetricasTreinamento")
dados_treinamento_df <- dbReadTable(con, "DadosTreinamento")
status_hub_df <- dbReadTable(con, "StatusHub")

dbDisconnect(con)
print("INFO: Dados carregados do banco de dados com sucesso.")


# --- ETAPA 3: PROCESSAR DADOS ---
# Função auxiliar robusta para converter um blob (lista) em um vetor numérico
blob_to_numeric <- function(col) {
  sapply(col, function(x) {
    if (is.raw(x)) {
      if (length(x) == 0) return(NA_real_)
      # Python/SQLite armazena REAL como double de 8 bytes
      return(readBin(x, what = "double", size = 8, n = 1))
    }
    # Fallback para caso o dado já seja numérico ou convertível
    return(as.numeric(x))
  })
}

# Conversão de timestamps e tipos de dados
if (nrow(leituras_sensores_df) > 0) {
  leituras_sensores_df <- leituras_sensores_df %>% mutate(timestamp = ymd_hms(timestamp_iso))
}

if (nrow(analises_pois_df) > 0) {
  analises_pois_df <- analises_pois_df %>%
    # Aplica a conversão robusta em todas as colunas numéricas/inteiras
    mutate(
      prob_geo_inundacao = blob_to_numeric(prob_geo_inundacao),
      latitude_poi = blob_to_numeric(latitude_poi),
      longitude_poi = blob_to_numeric(longitude_poi),
      risco_geo_alto_bool = as.integer(blob_to_numeric(risco_geo_alto_bool)),
      raio_buffer_impacto_m = as.integer(blob_to_numeric(raio_buffer_impacto_m)),
      timestamp_ciclo = ymd_hms(timestamp_ciclo_iso)
    )
}

if (nrow(status_hub_df) > 0) {
    status_hub_df <- status_hub_df %>%
    mutate(
        across(c(uptime_segundos, ciclos_decisao_executados, mensagens_mqtt_recebidas, alertas_sistema_enviados), blob_to_numeric),
        timestamp_status = ymd_hms(timestamp_status_iso)
    )
}
print("INFO: Processamento de datas e tipos de dados concluído.")


# --- ETAPA 4: GERAR GRÁFICOS E ANÁLISES ---
output_dir <- file.path("output", "analysis")
dir.create(output_dir, showWarnings = FALSE, recursive = TRUE)

theme_set(theme_minimal(base_size = 14) +
          theme(plot.title = element_text(hjust = 0.5, face = "bold"),
                plot.subtitle = element_text(hjust = 0.5),
                plot.caption = element_text(hjust = 1, color = "grey40"),
                panel.grid.minor = element_blank()))

# Análise 1: Série Temporal dos Sensores
if (nrow(leituras_sensores_df) > 1) {
  sensor_data_processed <- leituras_sensores_df %>%
    filter(tipo_sensor %in% c("nivel_agua", "qtd_chuva")) %>%
    mutate(
      valor_numerico = case_when(
        categoria_valor %in% c("Baixo", "Nenhuma", "Leve") ~ 1,
        categoria_valor %in% c("Medio", "Moderada") ~ 2,
        categoria_valor %in% c("Alto", "Pesada") ~ 3,
        TRUE ~ 0
      ),
      tipo_sensor_pt = recode(tipo_sensor, "nivel_agua" = "Nível da Água", "qtd_chuva" = "Quantidade de Chuva")
    )
  
  plot1 <- ggplot(sensor_data_processed, aes(x = timestamp, y = valor_numerico, color = tipo_sensor_pt)) +
    geom_line(alpha = 0.5) + geom_point(size = 3) +
    facet_wrap(~tipo_sensor_pt, ncol = 1, scales = "free_y") +
    scale_y_continuous(breaks = 1:3, labels = c("Baixo/Leve", "Médio/Moderado", "Alto/Pesado")) +
    labs(title = "Série Temporal das Leituras dos Sensores", x = "Data e Hora", y = "Nível da Categoria", color = "Tipo de Sensor", caption = "Fonte: Tabela LeiturasSensores") +
    theme(legend.position = "none")
  
  ggsave(file.path(output_dir, "analise_1_serie_temporal_sensores.png"), plot1, width = 12, height = 8, dpi = 150)
  print("INFO: Gráfico 1 (Série Temporal dos Sensores) salvo.")
}

# Análise 2: Risco por Categoria de Chuva
if (nrow(analises_pois_df) > 0) {
  risco_por_chuva <- analises_pois_df %>%
    filter(categoria_chuva_sensor_no_ciclo %in% c("Nenhuma", "Leve", "Moderada", "Pesada")) %>%
    mutate(
      status_risco = if_else(grepl("ALTO RISCO", status_combinado_poi), "Alto Risco", "Baixo Risco/OK"),
      categoria_chuva_sensor_no_ciclo = factor(categoria_chuva_sensor_no_ciclo, levels = c("Nenhuma", "Leve", "Moderada", "Pesada"))
    ) %>%
    count(categoria_chuva_sensor_no_ciclo, status_risco)

  plot2 <- ggplot(risco_por_chuva, aes(x = categoria_chuva_sensor_no_ciclo, y = n, fill = status_risco)) +
    geom_bar(stat = "identity", position = "stack") +
    scale_fill_manual(values = c("Alto Risco" = "#d9534f", "Baixo Risco/OK" = "#5cb85c")) +
    geom_text(aes(label = n), position = position_stack(vjust = 0.5), size = 4, color = "white", fontface = "bold") +
    labs(title = "Contagem de Alertas de Risco por Categoria de Chuva", x = "Categoria da Chuva no Ciclo de Análise", y = "Número de Análises de POIs", fill = "Status de Risco Combinado", caption = "Fonte: Tabela AnalisesPOIs")
  
  ggsave(file.path(output_dir, "analise_2_risco_por_chuva.png"), plot2, width = 10, height = 7, dpi = 150)
  print("INFO: Gráfico 2 (Risco por Categoria de Chuva) salvo.")
}

# Análise 3: Mapa Geográfico de Risco dos POIs
if (nrow(analises_pois_df) > 0) {
  poi_summary <- analises_pois_df %>%
    group_by(nome_poi, latitude_poi, longitude_poi) %>%
    summarise(
      prob_media = mean(prob_geo_inundacao, na.rm = TRUE),
      n_alertas_alto_risco = sum(grepl("ALTO RISCO", status_combinado_poi)),
      .groups = 'drop'
    ) %>%
    st_as_sf(coords = c("longitude_poi", "latitude_poi"), crs = 4326)

  tryCatch({
    plot3 <- ggplot() +
      annotation_map_tile(type = "cartolight", zoom = 12) + 
      geom_sf(data = poi_summary, aes(color = prob_media, size = n_alertas_alto_risco), alpha = 0.8) +
      geom_sf_text(data = poi_summary, aes(label = nome_poi), nudge_y = 0.005, size = 3.5, fontface = "bold", check_overlap = TRUE) +
      scale_color_gradient(low = "green", high = "red") +
      labs(title = "Mapa de Risco dos Pontos de Interesse (POIs)", color = "Prob. Média\nde Inundação", size = "Nº de Alertas\nde Alto Risco", caption = "Fonte: Tabela AnalisesPOIs") +
      theme(axis.title = element_blank())
    
    ggsave(file.path(output_dir, "analise_3_mapa_risco_pois.png"), plot3, width = 10, height = 10, dpi = 150)
    print("INFO: Gráfico 3 (Mapa de Risco dos POIs) salvo.")
  }, error = function(e) { print(paste("AVISO: Não foi possível gerar o mapa de risco (Gráfico 3).", e$message)) })
}

# Análise 4: Visualização da Performance do Modelo
if (nrow(metricas_treinamento_df) > 0) {
  latest_training <- metricas_treinamento_df %>%
    arrange(desc(timestamp_treinamento_iso)) %>%
    slice(1)
  
  metricas <- fromJSON(latest_training$metricas_json)
  cm <- as.data.frame(metricas$matriz_confusao)
  cm_df <- data.frame(
    Predito = factor(c("Não Inundado", "Inundado", "Não Inundado", "Inundado"), levels = c("Inundado", "Não Inundado")),
    Real = factor(c("Não Inundado", "Não Inundado", "Inundado", "Inundado"), levels = c("Inundado", "Não Inundado")),
    N = c(cm$VN, cm$FN, cm$FP, cm$VP)
  )

  plot4 <- ggplot(cm_df, aes(x = Predito, y = Real, fill = N)) +
    geom_tile(color = "white", linewidth = 1.5) +
    geom_text(aes(label = N), size = 6, color = "white", fontface = "bold") +
    scale_fill_gradient(low = "grey60", high = "firebrick") +
    labs(title = "Matriz de Confusão do Último Treinamento", subtitle = paste("Modelo:", latest_training$nome_modelo_salvo), x = "Classe Predita", y = "Classe Real", caption = "Fonte: Tabela MetricasTreinamento") +
    theme(legend.position = "none")

  ggsave(file.path(output_dir, "analise_4_matriz_confusao.png"), plot4, width = 8, height = 7, dpi = 150)
  print("INFO: Gráfico 4 (Matriz de Confusão) salvo.")
}

# Análise 5: Distribuição de Features do Dataset de Treinamento
if (nrow(dados_treinamento_df) > 0) {
  dados_treinamento_long <- dados_treinamento_df %>%
    select(elevation, distance_to_river, is_flooded) %>%
    mutate(is_flooded = factor(is_flooded, levels = c(0, 1), labels = c("Não Inundado", "Inundado"))) %>%
    pivot_longer(cols = c(elevation, distance_to_river), names_to = "feature", values_to = "value")

  plot5 <- ggplot(dados_treinamento_long, aes(x = value, fill = is_flooded)) +
    geom_density(alpha = 0.6) +
    facet_wrap(~feature, scales = "free") +
    scale_fill_manual(values = c("Não Inundado" = "darkgreen", "Inundado" = "darkred")) +
    labs(title = "Distribuição de Features Chave por Classe de Inundação", x = "Valor da Feature", y = "Densidade", fill = "Classe", caption = "Fonte: Tabela DadosTreinamento")
  
  ggsave(file.path(output_dir, "analise_5_distribuicao_features.png"), plot5, width = 12, height = 6, dpi = 150)
  print("INFO: Gráfico 5 (Distribuição de Features) salvo.")
}


print("\nAnálise em R concluída. Verifique os arquivos .png gerados na pasta 'output/analysis/'.")