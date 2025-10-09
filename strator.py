import pandas as pd
import numpy as np
from openpyxl import load_workbook
import streamlit as st
from io import BytesIO

# ================= Interface utilisateur =================
st.title("📊 Générateur d'écritures analytiques - BLDD Edition")

fichier_entree = st.file_uploader("📂 Importer le fichier Excel BLDD", type=["xlsx"])
date_ecriture = st.date_input("📅 Date d'écriture")
journal = st.text_input("📒 Journal", value="VT")
libelle_base = st.text_input("📝 Libellé", value="VENTES BLDD")

# Comptes
compte_ca_brut = st.text_input("💰 Compte CA Brut", value="701100000")
compte_retours = st.text_input("💰 Compte Retours", value="709000000")
compte_remises = st.text_input("💰 Compte Remises libraires", value="709100000")
compte_tva = st.text_input("💰 Compte TVA collectée", value="445710060")
compte_tva_com = st.text_input("💰 Compte TVA sur commissions", value="445660")
compte_com_dist = st.text_input("💰 Compte Commissions distribution", value="622800000")
compte_com_diff = st.text_input("💰 Compte Commissions diffusion", value="622800010")
compte_prov_debit = st.text_input("💰 Compte Provision Retours Débit", value="681000000")
compte_prov_credit = st.text_input("💰 Compte Provision Retours Crédit", value="151000000")

# Taux et montants
taux_dist = st.number_input("Taux distribution (%)", value=12.5) / 100
taux_diff = st.number_input("Taux diffusion (%)", value=9.0) / 100
taux_tva = st.number_input("TVA ventes (%)", value=5.5) / 100
taux_tva_com = st.number_input("TVA commissions (%)", value=5.5) / 100

# Montants totaux commissions et reprise provision
com_distribution_total = st.number_input("Montant total commissions distribution", value=1000.00, format="%.2f")
com_diffusion_total = st.number_input("Montant total commissions diffusion", value=500.00, format="%.2f")
reprise_prov = st.number_input("Montant reprise provision 6 mois", value=0.0, format="%.2f")

# ================= Traitement =================
if fichier_entree is not None:
    df = pd.read_excel(fichier_entree, header=9, dtype={"ISBN": str})
    df.columns = df.columns.str.strip()
    df = df.dropna(subset=["ISBN"]).copy()
    
    # Nettoyage ISBN
    df["ISBN"] = df["ISBN"].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df["ISBN"] = df["ISBN"].str.replace('-', '', regex=False).str.replace(' ', '', regex=False)
    
    # Colonnes numériques
    for c in ["Vente", "Retour", "Net", "Facture"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).round(2)
    
    # Calcul remises libraires
    df["Remises"] = df["Net"] - df["Facture"]
    
    # ========== Distribution commissions ==========
    # Distribution
    raw_dist = df["Vente"] * taux_dist
    sum_raw_dist = raw_dist.sum()
    scaled_dist = raw_dist * (com_distribution_total / sum_raw_dist)
    
    cents_floor = np.floor(scaled_dist * 100).astype(int)
    remainders = (scaled_dist * 100) - cents_floor
    target_cents = int(round(com_distribution_total * 100))
    diff = target_cents - cents_floor.sum()
    idx_sorted = np.argsort(-remainders.values)
    adjust = np.zeros(len(df), dtype=int)
    if diff > 0:
        adjust[idx_sorted[:diff]] = 1
    elif diff < 0:
        adjust[idx_sorted[len(df)+diff:]] = -1
    df["Commission_distribution"] = (cents_floor + adjust) / 100.0
    
    # Diffusion
    raw_diff = df["Net"] * taux_diff
    sum_raw_diff = raw_diff.sum()
    scaled_diff = raw_diff * (com_diffusion_total / sum_raw_diff)
    
    cents_floor = np.floor(scaled_diff * 100.0).astype(int)
    remainders = (scaled_diff * 100.0) - cents_floor
    target_cents = int(round(com_diffusion_total * 100))
    diff = target_cents - cents_floor.sum()
    idx_sorted = np.argsort(-remainders.values)
    adjust = np.zeros(len(df), dtype=int)
    if diff > 0:
        adjust[idx_sorted[:diff]] = 1
    elif diff < 0:
        adjust[idx_sorted[len(df)+diff:]] = -1
    df["Commission_diffusion"] = (cents_floor + adjust) / 100.0
    
    # ================= Construction écritures =================
    ecritures = []
    
    # CA Brut
    for _, r in df.iterrows():
        if r["Vente"] != 0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"),
                "Journal": journal,
                "Compte": compte_ca_brut,
                "Libelle": f"{libelle_base} - CA brut ISBN",
                "ISBN": r["ISBN"],
                "Débit": 0.0,
                "Crédit": r["Vente"]
            })
    
    # Retours (positif en débit)
    for _, r in df.iterrows():
        if r["Retour"] != 0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"),
                "Journal": journal,
                "Compte": compte_retours,
                "Libelle": f"{libelle_base} - Retours ISBN",
                "ISBN": r["ISBN"],
                "Débit": abs(r["Retour"]),
                "Crédit": 0.0
            })
    
    # Remises libraires
    for _, r in df.iterrows():
        if r["Remises"] != 0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"),
                "Journal": journal,
                "Compte": compte_remises,
                "Libelle": f"{libelle_base} - Remises ISBN",
                "ISBN": r["ISBN"],
                "Débit": abs(r["Remises"]),
                "Crédit": 0.0
            })
    
    # TVA collectée (globale)
    ca_net_global = df["Facture"].sum()
    tva_collectee = round(ca_net_global * taux_tva, 2)
    ecritures.append({
        "Date": date_ecriture.strftime("%d/%m/%Y"),
        "Journal": journal,
        "Compte": compte_tva,
        "Libelle": f"{libelle_base} - TVA ventes",
        "ISBN": "",
        "Débit": 0.0,
        "Crédit": tva_collectee
    })
    
    # Commissions distribution et diffusion
    for _, r in df.iterrows():
        if r["Commission_distribution"] != 0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"),
                "Journal": journal,
                "Compte": compte_com_dist,
                "Libelle": f"{libelle_base} - Com. distribution ISBN",
                "ISBN": r["ISBN"],
                "Débit": r["Commission_distribution"],
                "Crédit": 0.0
            })
        if r["Commission_diffusion"] != 0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"),
                "Journal": journal,
                "Compte": compte_com_diff,
                "Libelle": f"{libelle_base} - Com. diffusion ISBN",
                "ISBN": r["ISBN"],
                "Débit": r["Commission_diffusion"],
                "Crédit": 0.0
            })
    
    # TVA déductible sur commissions (globale)
    tva_com = round((df["Commission_distribution"].sum() + df["Commission_diffusion"].sum()) * taux_tva_com, 2)
    ecritures.append({
        "Date": date_ecriture.strftime("%d/%m/%Y"),
        "Journal": journal,
        "Compte": compte_tva_com,
        "Libelle": f"{libelle_base} - TVA sur commissions",
        "ISBN": "",
        "Débit": tva_com,
        "Crédit": 0.0
    })
    
    # Provisions pour retours
    prov_retour = round(df["Vente"].sum() * 1.055 * 0.10, 2)  # 10% TTC
    # Débit 681
    ecritures.append({
        "Date": date_ecriture.strftime("%d/%m/%Y"),
        "Journal": journal,
        "Compte": compte_prov_debit,
        "Libelle": f"{libelle_base} - Provision retours",
        "ISBN": "",
        "Débit": prov_retour,
        "Crédit": 0.0
    })
    # Crédit 151
    ecritures.append({
        "Date": date_ecriture.strftime("%d/%m/%Y"),
        "Journal": journal,
        "Compte": compte_prov_credit,
        "Libelle": f"{libelle_base} - Provision retours",
        "ISBN": "",
        "Débit": 0.0,
        "Crédit": prov_retour
    })
    
    # Reprise provision ancienne
    if reprise_prov != 0:
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_prov_debit,
            "Libelle": f"{libelle_base} - Reprise ancienne provision",
            "ISBN": "",
            "Débit": 0.0,
            "Crédit": reprise_prov
        })
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_prov_credit,
            "Libelle": f"{libelle_base} - Reprise ancienne provision",
            "ISBN": "",
            "Débit": reprise_prov,
            "Crédit": 0.0
        })
    
    df_ecr = pd.DataFrame(ecritures)
    
    # Vérification équilibre
    total_debit = round(df_ecr["Débit"].sum(), 2)
    total_credit = round(df_ecr["Crédit"].sum(), 2)
    if total_debit != total_credit:
        st.error(f"⚠️ Écriture déséquilibrée : Débit={total_debit}, Crédit={total_credit}")
    else:
        st.success("✅ Écritures équilibrées !")
    
    # Export Excel
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_ecr.to_excel(writer, index=False, sheet_name="Ecritures")
    buffer.seek(0)
    
    st.download_button(
        label="📥 Télécharger les écritures (Excel)",
        data=buffer,
        file_name="Ecritures_BLDD.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    
    # Aperçu
    st.subheader("👀 Aperçu des écritures générées")
    st.dataframe(df_ecr)
