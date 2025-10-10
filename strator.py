import streamlit as st
import pandas as pd

st.header("📘 Génération des écritures comptables - Maison d’édition")

# --- Paramètres utilisateur ---
journal = st.text_input("📒 Journal", value="VT")
date_ecriture = st.date_input("📅 Date de l’écriture")
montant_reprise = st.number_input("💸 Montant de la reprise de provision", min_value=0.0, value=0.0, step=100.0)

# --- Import du fichier source ---
fichier = st.file_uploader("📂 Importer le fichier BLDD (Excel ou CSV)", type=["xlsx", "csv"])

if fichier:
    if fichier.name.endswith(".csv"):
        df = pd.read_csv(fichier, sep=";", decimal=",")
    else:
        df = pd.read_excel(fichier)

    # Vérification des colonnes
    st.write("Colonnes détectées :", df.columns.tolist())

    # --- Nettoyage et calculs ---
    # Ajuste selon tes colonnes réelles
    if "Facture" in df.columns and "Net" in df.columns:
        df["CA_brut"] = df["Facture"] + df["Net"]
    elif "CA_brut" not in df.columns:
        st.error("❌ Impossible de calculer le CA brut (colonnes 'Facture' et 'Net' manquantes).")
        st.stop()

    ca_ttc = df["CA_brut"].sum()

    # --- Calcul de la provision (10 % du CA TTC) ---
    provision_retour = round(ca_ttc * 0.10, 2)

    # --- Commissions et TVA déductible ---
    com622800 = df["Montant_622800"].sum() if "Montant_622800" in df else 0
    com622801 = df["Montant_622801"].sum() if "Montant_622801" in df else 0
    base_tva = com622800 + com622801
    tva_deductible = round(base_tva * 0.055, 2)

    # --- Construction des écritures ---
    ecritures = []

    # 1️⃣ Dotation provision (681 analytique)
    ecritures.append({
        "Date": date_ecriture,
        "Journal": journal,
        "Compte": "681100000",
        "Libellé": "Dotation provision retours (10%)",
        "Débit": provision_retour,
        "Crédit": 0,
        "Analytique": "Provision_retour"
    })

    # 2️⃣ Reprise de provision (si renseignée)
    if montant_reprise > 0:
        ecritures.append({
            "Date": date_ecriture,
            "Journal": journal,
            "Compte": "467100000",
            "Libellé": "Reprise provision retours",
            "Débit": montant_reprise,
            "Crédit": 0,
            "Analytique": "Reprise_provision"
        })
        ecritures.append({
            "Date": date_ecriture,
            "Journal": journal,
            "Compte": "411100000",
            "Libellé": "Reprise provision retours",
            "Débit": 0,
            "Crédit": montant_reprise,
            "Analytique": "Reprise_provision"
        })

    # 3️⃣ TVA déductible sur commissions
    if tva_deductible > 0:
        ecritures.append({
            "Date": date_ecriture,
            "Journal": journal,
            "Compte": "445660000",
            "Libellé": "TVA déductible commissions (5,5%)",
            "Débit": tva_deductible,
            "Crédit": 0,
            "Analytique": "Commissions"
        })

    # 4️⃣ Vente (CA TTC)
    ecritures.append({
        "Date": date_ecriture,
        "Journal": journal,
        "Compte": "706000000",
        "Libellé": "Vente de livres TTC",
        "Débit": 0,
        "Crédit": ca_ttc,
        "Analytique": "Vente"
    })

    # --- Équilibrage automatique ---
    df_ecrit = pd.DataFrame(ecritures)
    total_debit = df_ecrit["Débit"].sum()
    total_credit = df_ecrit["Crédit"].sum()
    ecart = round(total_debit - total_credit, 2)

    # Si écart positif → 4111 au crédit ; sinon au débit
    if ecart > 0:
        ecritures.append({
            "Date": date_ecriture,
            "Journal": journal,
            "Compte": "411100000",
            "Libellé": "Solde client (équilibrage)",
            "Débit": 0,
            "Crédit": ecart,
            "Analytique": ""
        })
    elif ecart < 0:
        ecritures.append({
            "Date": date_ecriture,
            "Journal": journal,
            "Compte": "411100000",
            "Libellé": "Solde client (équilibrage)",
            "Débit": abs(ecart),
            "Crédit": 0,
            "Analytique": ""
        })

    # --- Résultat final ---
    df_final = pd.DataFrame(ecritures)
    total_debit_final = df_final["Débit"].sum()
    total_credit_final = df_final["Crédit"].sum()

    st.dataframe(df_final, use_container_width=True)
    st.write(f"✅ **Total Débit :** {total_debit_final:,.2f} €")
    st.write(f"✅ **Total Crédit :** {total_credit_final:,.2f} €")
    st.write(f"⚖️ **Équilibre final :** {round(total_debit_final - total_credit_final, 2)} €")
