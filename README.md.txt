# Repricer Ready Pro + Keepa Streamlit App

Questa applicazione Streamlit permette di caricare dati da file Excel di Keepa e CSV di Ready Pro (Inserzioni Amazon), unirli, calcolare margini e differenziali di prezzo, e riesportare i dati aggiornati per Ready Pro.

## 🎯 Funzionalità Principali

1.  **Caricamento File**:
    *   `keepa.xlsx`: Richiede colonne `ASIN`, `Locale`, `BuyBox_Current`, `Category`.
    *   `Inserzioni Amazon.CSV`: File CSV standard di Ready Pro con colonne come `SKU`, `Codice`, `Descrizione`, `Sito`, `Prezzo`, ecc.
2.  **Mapping Locale → Sito**: Converte i codici `Locale` di Keepa nei formati `Sito` di Amazon (es. `it` → `Italia - Amazon.it`).
3.  **Unione Dati**: Unisce i due dataset basandosi su `(ASIN/Codice, Sito)`.
4.  **Griglia Editabile**: Mostra i dati in una griglia `st-aggrid` con:
    *   Colonne originali di Ready Pro.
    *   Colonne calcolate:
        *   `buybox_price` (da Keepa)
        *   `diff_euro` (`buybox_price` − `nostro_prezzo`)
        *   `diff_pct` (`(buybox_price / nostro_prezzo − 1) × 100`)
        *   `amazon_fee_pct` (valore globale impostabile tramite slider, default 15%)
        *   `shipping_cost` (default 5,14 € per Italia, 11,50 € altrimenti; cella editabile)
        *   `net_margin` (`nostro_prezzo` − `(amazon_fee_pct % di nostro_prezzo)` − `shipping_cost`)
    *   Evidenziazione in rosso per righe con `net_margin < 0`.
5.  **Azioni di Massa sulla Toolbar**:
    *   "Scala prezzo": Applica uno sconto di −X € o −Y % sulle righe selezionate.
    *   "Allinea a Buy Box – Δ": Imposta `prezzo = buybox_price − Δ` (Δ in euro o %) per le righe selezionate.
6.  **Aggiornamenti Live**: Le colonne calcolate si aggiornano automaticamente dopo ogni modifica nella griglia o cambio dei parametri globali.
7.  **Esportazione**: Genera un file CSV per Ready Pro, identico al file caricato (stesso separatore `;`, stesse colonne/ordine, encoding UTF-8-BOM) ma con la colonna `Prezzo` aggiornata.
8.  **Logging**: Registra le operazioni e gli errori su `repricer.log` (con rotazione settimanale).

## 🛠️ Requisiti Tecnici

*   Python ≥ 3.12
*   Vedere `requirements.txt` per le dipendenze.

## 🚀 Quick Start

1.  **Clona il repository o scarica i file.**
    ```bash
    # Se usi git
    # git clone <repository_url>
    # cd repricer-ready-pro-keepa
    ```

2.  **Crea un ambiente virtuale (consigliato) e attivalo:**
    ```bash
    python -m venv venv
    # Windows
    venv\Scripts\activate
    # macOS/Linux
    source venv/bin/activate
    ```

3.  **Installa le dipendenze:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Esegui l'applicazione Streamlit:**
    ```bash
    streamlit run app.py
    ```

5.  Apri il browser all'indirizzo fornito da Streamlit (solitamente `http://localhost:8501`).

## 📁 Struttura del Progetto
.
├── app.py # Script principale dell'applicazione Streamlit
├── services/ # Moduli di servizio
│ ├── init.py
│ ├── io_layer.py # Caricamento/salvataggio file e validazioni
│ ├── pricing.py # Logica di calcolo prezzi, margini, azioni di massa
│ ├── mapping.py # Utility per mapping Sito↔Locale
│ └── keepa.py # Stub per futura integrazione API Keepa
├── config/ # File di configurazione
│ └── amazon_fees.yml # Configurazione commissioni Amazon (es. default_fee_pct)
├── tests/ # Test unitari (pytest)
│ ├── init.py
│ ├── conftest.py # Fixtures per i test
│ └── test_pricing.py # Esempio di test per le funzioni di pricing
├── README.md # Questo file
├── requirements.txt # Dipendenze Python
└── .gitignore # File ignorati da Git (es. repricer.log)
└── repricer.log # File di log generato dall'applicazione
## 📝 Note

*   Assicurati che i file `keepa.xlsx` e `Inserzioni Amazon.CSV` abbiano le colonne richieste e i formati corretti.
*   Eventuali errori di formato dei file verranno mostrati nell'interfaccia e registrati nel file `repricer.log`.
*   L'esportazione del CSV per Ready Pro utilizza il separatore `;`, decimali con `,` e encoding UTF-8 con BOM.