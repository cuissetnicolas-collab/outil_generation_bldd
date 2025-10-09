import pandas as pd
import numpy as np
from io import BytesIO
import streamlit as st

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
compte_tva = st.text_input("💰 Compte TVA collectée", value="445710060")
compte_com_dist = st.text_input("💰 Compte Commissions distribution", value="622800000")
compte_com_diff = st.text_input("💰 Compte Commissions diffusion", value="622800010")
compte_tva_com = st.text_input("💰 Compte TVA sur commissions", value="445660000")
compte_prov_retour = st.text_input("💰 Compte Provision retour débit", value="681000000")
compte_prov_retour_credit = st.text_input("💰 Compte Provision retour crédit", value="151000000")

# 🔹 Saisie des montants commissions et provisions
com_distribution_total = st.number_input("Montant total commissions distribution", value=1000.00, format="%.2f")
com_diffusion_total = st.number_input("Montant total commissions diffusion", value=500.00, format="%.2f")
provision_ancienne = st.number_input("Reprise ancienne provision pour retours", value=0.0, format="%.2f")

# Taux
taux_dist = st.number_input("Taux distribution (%)", value=12.5)/100
taux_diff = st.number_input("Taux diffusion (%)", value=9.0)/100
taux_tva = 5.5/100
taux_prov_retour = 0.10  # 10% TTC sur CA brut

# ========== Traitement ==========
if fichier_entree is not None:
    df = pd.read_excel(fichier_entree, header=9, dtype={"ISBN": str})
    df.columns = df.columns.str.strip()
    df = df.dropna(subset=["ISBN"]).copy()
    df["ISBN"] = df["ISBN"].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df["ISBN"] = df["ISBN"].str.replace('-', '', regex=False).str.replace(' ', '', regex=False)

    # Colonnes numériques
    for c in ["Vente", "Retour", "Net", "Facture"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).round(2)

    # 🔹 Commissions distribution
    raw_dist = df["Net"] * taux_dist
    sum_raw_dist = raw_dist.sum()
    scaled_dist = raw_dist * (com_distribution_total / sum_raw_dist)
    cents_floor = np.floor(scaled_dist * 100).astype(int)
    remainders = (scaled_dist * 100) - cents_floor
    diff = int(round(com_distribution_total*100)) - cents_floor.sum()
    idx_sorted = np.argsort(-remainders.values)
    adjust = np.zeros(len(df), dtype=int)
    if diff > 0:
        adjust[idx_sorted[:diff]] = 1
    elif diff < 0:
        adjust[idx_sorted[len(df)+diff:]] = -1
    df["Commission_distribution"] = (cents_floor + adjust)/100.0

    # 🔹 Commissions diffusion
    raw_diff = df["Net"] * taux_diff
    sum_raw_diff = raw_diff.sum()
    scaled_diff = raw_diff * (com_diffusion_total / sum_raw_diff)
    cents_floor = np.floor(scaled_diff * 100).astype(int)
    remainders = (scaled_diff * 100) - cents_floor
    diff = int(round(com_diffusion_total*100)) - cents_floor.sum()
    idx_sorted = np.argsort(-remainders.values)
    adjust = np.zeros(len(df), dtype=int)
    if diff > 0:
        adjust[idx_sorted[:diff]] = 1
    elif diff < 0:
        adjust[idx_sorted[len(df)+diff:]] = -1
    df["Commission_diffusion"] = (cents_floor + adjust)/100.0

    # 🔹 Provisions pour retours
    df["Provision_retour"] = df["Vente"] * (1 + taux_tva) * taux_prov_retour

    # 🔹 Calcul remises libraires
    df["Remise_libraire"] = df["Net"] - df["Facture"]

    # 🔹 TVA collectée sur CA net après remise et retours
    df["TVA"] = (df["Facture"] * taux_tva).round(2)

    # ========== Construction écritures ==========
    ecritures = []

    # CA brut
    for _, r in df.iterrows():
        if r["Vente"] != 0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal,
                "Compte": compte_ca_brut, "Libelle": f"{libelle_base} - CA Brut",
                "ISBN": r["ISBN"], "Débit": 0.0, "Crédit": r["Vente"]
            })

    # Retours
    for _, r in df.iterrows():
        if r["Retour"] != 0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal,
                "Compte": compte_retours, "Libelle": f"{libelle_base} - Retours",
                "ISBN": r["ISBN"], "Débit": r["Retour"], "Crédit": 0.0
            })

    # Remises libraires
    for _, r in df.iterrows():
        if r["Remise_libraire"] != 0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal,
                "Compte": compte_remises, "Libelle": f"{libelle_base} - Remises libraires",
                "ISBN": r["ISBN"], "Débit": r["Remise_libraire"], "Crédit": 0.0
            })

    # TVA collectée
    tva_total = df["TVA"].sum().round(2)
    if tva_total != 0:
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal,
            "Compte": compte_tva, "Libelle": f"{libelle_base} - TVA collectée",
            "ISBN": "", "Débit": 0.0, "Crédit": tva_total
        })

    # Commissions distribution
    for _, r in df.iterrows():
        if r["Commission_distribution"] != 0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal,
                "Compte": compte_com_dist, "Libelle": f"{libelle_base} - Com. distribution",
                "ISBN": r["ISBN"], "Débit": r["Commission_distribution"], "Crédit": 0.0
            })
            # TVA déductible sur commission
            tva_com = round(r["Commission_distribution"]*taux_tva,2)
            if tva_com != 0:
                ecritures.append({
                    "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal,
                    "Compte": compte_tva_com, "Libelle": f"{libelle_base} - TVA déductible commission dist",
                    "ISBN": r["ISBN"], "Débit": 0.0, "Crédit": tva_com
                })

    # Commissions diffusion
    for _, r in df.iterrows():
        if r["Commission_diffusion"] != 0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal,
                "Compte": compte_com_diff, "Libelle": f"{libelle_base} - Com. diffusion",
                "ISBN": r["ISBN"], "Débit": r["Commission_diffusion"], "Crédit": 0.0
            })
            tva_com = round(r["Commission_diffusion"]*taux_tva,2)
            if tva_com != 0:
                ecritures.append({
                    "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal,
                    "Compte": compte_tva_com, "Libelle": f"{libelle_base} - TVA déductible commission diff",
                    "ISBN": r["ISBN"], "Débit": 0.0, "Crédit": tva_com
                })

    # Provisions pour retours
    for _, r in df.iterrows():
        if r["Provision_retour"] != 0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal,
                "Compte": compte_prov_retour, "Libelle": f"{libelle_base} - Provision retours",
                "ISBN": "", "Débit": r["Provision_retour"], "Crédit": 0.0
            })
    # Reprise ancienne provision
    if provision_ancienne != 0:
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal,
            "Compte": compte_prov_retour_credit, "Libelle": f"{libelle_base} - Reprise ancienne provision",
            "ISBN": "", "Débit": 0.0, "Crédit": provision_ancienne
        })

    df_ecr = pd.DataFrame(ecritures)

    # Vérification équilibre
    total_debit = round(df_ecr["Débit"].sum(), 2)
    total_credit = round(df_ecr["Crédit"].sum(), 2)
    if total_debit != total_credit:
        st.error(f"⚠️ Écriture déséquilibrée : Débit={total_debit}, Crédit={total_credit}")
    else:
        st.success("✅ Écritures équilibrées !")

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

    # Aperçu
    st.subheader("👀 Aperçu des écritures générées")
    st.dataframe(df_ecr)
