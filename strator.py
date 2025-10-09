import pandas as pd
import numpy as np
from openpyxl import load_workbook
import streamlit as st
from io import BytesIO

# ========== Interface utilisateur ==========
st.title("📊 Générateur d'écritures analytiques - BLDD")

fichier_entree = st.file_uploader("📂 Importer le fichier Excel BLDD", type=["xlsx"])
date_ecriture = st.date_input("📅 Date d'écriture")
journal = st.text_input("📒 Journal", value="VT")
libelle_base = st.text_input("📝 Libellé", value="VENTES BLDD")

# Comptes
compte_ca = st.text_input("💰 Compte CA Brut", value="701100000")
compte_retours = st.text_input("💰 Compte Retours", value="709000000")
compte_remise = st.text_input("💰 Compte Remises Libraires", value="709100000")
compte_com_dist = st.text_input("💰 Compte commissions distribution", value="622800000")
compte_com_diff = st.text_input("💰 Compte commissions diffusion", value="622800010")
compte_tva_col = st.text_input("💰 Compte TVA collectée", value="445710060")
compte_tva_ded = st.text_input("💰 Compte TVA déductible commissions", value="445660")
compte_prov_ret = st.text_input("💰 Compte provisions retours", value="151000000")
compte_charge_prov = st.text_input("💰 Compte charge provisions", value="681000000")

# 🔹 Saisie des taux et montants
taux_dist = st.number_input("Taux distribution (%)", value=12.5) / 100
taux_diff = st.number_input("Taux diffusion (%)", value=9.0) / 100
total_com_dist = st.number_input("Montant total commissions distribution", value=1000.00, format="%.2f")
total_com_diff = st.number_input("Montant total commissions diffusion", value=500.00, format="%.2f")
prov_ancienne = st.number_input("Reprise ancienne provision sur retours", value=0.0, format="%.2f")

# ========== Traitement ==========
if fichier_entree is not None:
    df = pd.read_excel(fichier_entree, header=9, dtype={"ISBN": str})
    df.columns = df.columns.str.strip()
    df = df.dropna(subset=["ISBN"]).copy()
    df["ISBN"] = df["ISBN"].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df["ISBN"] = df["ISBN"].str.replace('-', '', regex=False).str.replace(' ', '', regex=False)

    for c in ["Vente", "Retour", "Net", "Facture"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).round(2)

    # 🔹 Calcul remises
    df["Remise"] = df["Net"] - df["Facture"]

    # 🔹 Commissions distribution
    raw_dist = df["Vente"] * taux_dist
    scaled_dist = raw_dist * (total_com_dist / raw_dist.sum())
    cents_floor = np.floor(scaled_dist * 100).astype(int)
    remainders = (scaled_dist * 100) - cents_floor
    diff = int(round(total_com_dist * 100)) - cents_floor.sum()
    idx_sorted = np.argsort(-remainders.values)
    adjust = np.zeros(len(df), dtype=int)
    if diff > 0:
        adjust[idx_sorted[:diff]] = 1
    elif diff < 0:
        adjust[idx_sorted[len(df)+diff:]] = -1
    df["Commission_distribution"] = (cents_floor + adjust) / 100.0

    # 🔹 Commissions diffusion
    raw_diff = df["Net"] * taux_diff
    scaled_diff = raw_diff * (total_com_diff / raw_diff.sum())
    cents_floor = np.floor(scaled_diff * 100).astype(int)
    remainders = (scaled_diff * 100) - cents_floor
    diff = int(round(total_com_diff * 100)) - cents_floor.sum()
    idx_sorted = np.argsort(-remainders.values)
    adjust = np.zeros(len(df), dtype=int)
    if diff > 0:
        adjust[idx_sorted[:diff]] = 1
    elif diff < 0:
        adjust[idx_sorted[len(df)+diff:]] = -1
    df["Commission_diffusion"] = (cents_floor + adjust) / 100.0

    # 🔹 Génération des écritures
    ecritures = []

    for _, r in df.iterrows():
        # CA Brut
        if r["Vente"] != 0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"),
                "Journal": journal,
                "Compte": compte_ca,
                "Libelle": f"{libelle_base} - CA Brut",
                "ISBN": r["ISBN"],
                "Débit": 0.0,
                "Crédit": r["Vente"]
            })
        # Retours
        if r["Retour"] != 0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"),
                "Journal": journal,
                "Compte": compte_retours,
                "Libelle": f"{libelle_base} - Retours",
                "ISBN": r["ISBN"],
                "Débit": abs(r["Retour"]),
                "Crédit": 0.0
            })
        # Remises libraires
        if r["Remise"] != 0:
            if r["Remise"] > 0:
                debit_remise = r["Remise"]
                credit_remise = 0.0
            else:
                debit_remise = 0.0
                credit_remise = abs(r["Remise"])
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"),
                "Journal": journal,
                "Compte": compte_remise,
                "Libelle": f"{libelle_base} - Remises libraires",
                "ISBN": r["ISBN"],
                "Débit": debit_remise,
                "Crédit": credit_remise
            })
        # Commissions distribution
        if r["Commission_distribution"] != 0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"),
                "Journal": journal,
                "Compte": compte_com_dist,
                "Libelle": f"{libelle_base} - Com. distribution",
                "ISBN": r["ISBN"],
                "Débit": 0.0,
                "Crédit": r["Commission_distribution"]
            })
        # Commissions diffusion
        if r["Commission_diffusion"] != 0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"),
                "Journal": journal,
                "Compte": compte_com_diff,
                "Libelle": f"{libelle_base} - Com. diffusion",
                "ISBN": r["ISBN"],
                "Débit": 0.0,
                "Crédit": r["Commission_diffusion"]
            })

    df_ecr = pd.DataFrame(ecritures)

    # 🔹 TVA collectée globale
    ca_net_global = (df["Facture"]).sum()
    tva_col = ca_net_global * 5.5 / 100
    df_ecr = pd.concat([df_ecr, pd.DataFrame([{
        "Date": date_ecriture.strftime("%d/%m/%Y"),
        "Journal": journal,
        "Compte": compte_tva_col,
        "Libelle": f"{libelle_base} - TVA collectée",
        "ISBN": "",
        "Débit": 0.0,
        "Crédit": tva_col
    }])], ignore_index=True)

    # 🔹 TVA déductible commissions (au débit)
    tva_ded = (df["Commission_distribution"].sum() + df["Commission_diffusion"].sum()) * 5.5 / 100
    df_ecr = pd.concat([df_ecr, pd.DataFrame([{
        "Date": date_ecriture.strftime("%d/%m/%Y"),
        "Journal": journal,
        "Compte": compte_tva_ded,
        "Libelle": f"{libelle_base} - TVA déductible commissions",
        "ISBN": "",
        "Débit": tva_ded,
        "Crédit": 0.0
    }])], ignore_index=True)

    # 🔹 Provisions retours
    prov_retour = df["Vente"].sum() * 1.055 * 0.10  # TTC 10%
    df_ecr = pd.concat([df_ecr, pd.DataFrame([
        {
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_charge_prov,
            "Libelle": f"{libelle_base} - Provisions retours",
            "ISBN": "",
            "Débit": prov_retour,
            "Crédit": 0.0
        },
        {
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_prov_ret,
            "Libelle": f"{libelle_base} - Provisions retours",
            "ISBN": "",
            "Débit": 0.0,
            "Crédit": prov_retour - prov_ancienne
        }
    ])], ignore_index=True)

    # 🔹 Vérification équilibre
    total_debit = round(df_ecr["Débit"].sum(), 2)
    total_credit = round(df_ecr["Crédit"].sum(), 2)
    if total_debit != total_credit:
        st.error(f"⚠️ Écriture déséquilibrée : Débit={total_debit}, Crédit={total_credit}")
    else:
        st.success("✅ Écritures équilibrées !")

    # 🔹 Export Excel
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

    st.subheader("👀 Aperçu des écritures générées")
    st.dataframe(df_ecr)
