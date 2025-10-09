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
compte_ca_brut = st.text_input("💰 Compte CA Brut", value="701100000")
compte_retours = st.text_input("💰 Compte Retours", value="709000000")
compte_remises = st.text_input("💰 Compte Remises libraires", value="709100000")
compte_com_dist = st.text_input("💰 Compte Commissions distribution", value="622800000")
compte_com_diff = st.text_input("💰 Compte Commissions diffusion", value="622800010")
compte_tva = st.text_input("💰 Compte TVA collectée", value="445710060")
compte_tva_com = st.text_input("💰 Compte TVA déductible commissions", value="445660")
compte_provision = st.text_input("💰 Compte provision retours débit", value="681")
compte_provision_credit = st.text_input("💰 Compte provision retours crédit", value="151")
compte_client = st.text_input("💰 Contrepartie client", value="411100011")

# 🔹 Saisie des taux
taux_dist = st.number_input("Taux distribution (%)", value=12.5) / 100
taux_diff = st.number_input("Taux diffusion (%)", value=9.0) / 100

# 🔹 Saisie des montants totaux
com_distribution_total = st.number_input("Montant total commissions distribution", value=1000.00, format="%.2f")
com_diffusion_total = st.number_input("Montant total commissions diffusion", value=500.00, format="%.2f")
provision_reprise = st.number_input("Montant reprise provision ancienne", value=0.00, format="%.2f")

# ========== Traitement ==========
if fichier_entree is not None:
    df = pd.read_excel(fichier_entree, header=9, dtype={"ISBN": str})
    df.columns = df.columns.str.strip()
    df = df.dropna(subset=["ISBN"]).copy()

    df["ISBN"] = df["ISBN"].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df["ISBN"] = df["ISBN"].str.replace('-', '', regex=False).str.replace(' ', '', regex=False)

    for c in ["Vente", "Retour", "Net", "Facture"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).round(2)

    # Remises libraires
    df["Remise"] = df["Net"] - df["Facture"]

    # Corriger retours négatifs
    df["Retour"] = df["Retour"].abs()

    # ========== Distribution ==========
    raw_dist = df["Net"] * taux_dist
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

    # ========== Diffusion ==========
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

    # ========== Construction écritures analytiques ==========
    ecritures = []

    for _, r in df.iterrows():
        # CA brut
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal, "Compte": compte_ca_brut,
            "Libelle": f"{libelle_base} - CA Brut", "ISBN": r["ISBN"],
            "Débit": 0.0, "Crédit": r["Vente"]
        })
        # Retours
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal, "Compte": compte_retours,
            "Libelle": f"{libelle_base} - Retours", "ISBN": r["ISBN"],
            "Débit": r["Retour"], "Crédit": 0.0
        })
        # Remises libraires (si négatif, au crédit)
        remise = r["Remise"]
        if remise >= 0:
            debit, credit = remise, 0.0
        else:
            debit, credit = 0.0, -remise
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal, "Compte": compte_remises,
            "Libelle": f"{libelle_base} - Remises", "ISBN": r["ISBN"],
            "Débit": debit, "Crédit": credit
        })
        # Commissions distribution
        com_dist = r["Commission_distribution"]
        if com_dist >= 0:
            debit, credit = com_dist, 0.0
        else:
            debit, credit = 0.0, -com_dist
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal, "Compte": compte_com_dist,
            "Libelle": f"{libelle_base} - Com. distribution", "ISBN": r["ISBN"],
            "Débit": debit, "Crédit": credit
        })
        # Commissions diffusion
        com_diff = r["Commission_diffusion"]
        if com_diff >= 0:
            debit, credit = com_diff, 0.0
        else:
            debit, credit = 0.0, -com_diff
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal, "Compte": compte_com_diff,
            "Libelle": f"{libelle_base} - Com. diffusion", "ISBN": r["ISBN"],
            "Débit": debit, "Crédit": credit
        })

    df_ecr = pd.DataFrame(ecritures)

    # ========== Écritures globales ==========
    # TVA collectée
    ca_net = df["Facture"].sum()
    tva_collectee = round(ca_net * 0.055, 2)
    df_ecr = pd.concat([df_ecr, pd.DataFrame([{
        "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal, "Compte": compte_tva,
        "Libelle": f"{libelle_base} - TVA collectée", "ISBN": "",
        "Débit": 0.0, "Crédit": tva_collectee
    }])], ignore_index=True)

    # TVA sur commissions
    tva_com = round((df["Commission_distribution"].sum() + df["Commission_diffusion"].sum()) * 0.055, 2)
    df_ecr = pd.concat([df_ecr, pd.DataFrame([{
        "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal, "Compte": compte_tva_com,
        "Libelle": f"{libelle_base} - TVA déductible commissions", "ISBN": "",
        "Débit": tva_com, "Crédit": 0.0
    }])], ignore_index=True)

    # Provisions retours
    ca_ttc_brut = df["Vente"].sum()  # TTC à ajuster si nécessaire
    provision = round(ca_ttc_brut * 0.10, 2)
    df_ecr = pd.concat([df_ecr, pd.DataFrame([
        {
            "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal, "Compte": compte_provision,
            "Libelle": f"{libelle_base} - Provision retours", "ISBN": "",
            "Débit": provision, "Crédit": 0.0
        },
        {
            "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal, "Compte": compte_provision_credit,
            "Libelle": f"{libelle_base} - Provision retours crédit", "ISBN": "",
            "Débit": 0.0, "Crédit": provision_reprise
        }
    ])], ignore_index=True)

    # Contrepartie client globale
    total_debit = df_ecr["Débit"].sum()
    total_credit = df_ecr["Crédit"].sum()
    df_ecr = pd.concat([df_ecr, pd.DataFrame([{
        "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal, "Compte": compte_client,
        "Libelle": f"{libelle_base} - Contrepartie client", "ISBN": "",
        "Débit": total_credit, "Crédit": total_debit
    }])], ignore_index=True)

    # ========== Export & téléchargement ==========
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
