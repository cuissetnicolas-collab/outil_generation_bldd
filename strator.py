import pandas as pd
import numpy as np
from io import BytesIO
import streamlit as st

st.set_page_config(page_title="BLDD - Générateur écritures analytiques", layout="wide")
st.title("📊 Générateur d'écritures analytiques - BLDD")

# ========== Import fichier BLDD ==========
fichier_entree = st.file_uploader("📂 Importer le fichier Excel BLDD", type=["xlsx"])
date_ecriture = st.date_input("📅 Date d'écriture")
journal = st.text_input("📒 Journal", value="VT")
libelle_base = st.text_input("📝 Libellé", value="VENTES BLDD")

# Comptes
compte_ca = st.text_input("💰 Compte CA Brut", value="701100000")
compte_retour = st.text_input("💰 Compte Retours", value="709000000")
compte_remise = st.text_input("💰 Compte Remises libraires", value="709100000")
compte_com_dist = st.text_input("💰 Compte Commissions distribution", value="622800000")
compte_com_diff = st.text_input("💰 Compte Commissions diffusion", value="622800010")
compte_tva_collectee = st.text_input("💰 Compte TVA collectée", value="445710060")
compte_tva_deductible = st.text_input("💰 Compte TVA sur commissions", value="445660")
compte_prov_retour_debit = st.text_input("💰 Compte Provision retours (Débit)", value="681")
compte_prov_retour_credit = st.text_input("💰 Compte Provision retours (Crédit)", value="151")

# Saisie des montants totaux commissions et provisions
total_com_dist = st.number_input("Montant total commissions distribution", value=1000.00, format="%.2f")
total_com_diff = st.number_input("Montant total commissions diffusion", value=500.00, format="%.2f")
provision_ancienne = st.number_input("Reprise ancienne provision 6 mois", value=0.0, format="%.2f")

# Taux commissions
taux_dist = st.number_input("Taux distribution (%)", value=12.5) / 100
taux_diff = st.number_input("Taux diffusion (%)", value=9.0) / 100

# Provision retours
taux_prov_retour = 10 / 100  # 10% TTC

if fichier_entree is not None:
    df = pd.read_excel(fichier_entree, header=9, dtype={"ISBN": str})
    df.columns = df.columns.str.strip()
    df = df.dropna(subset=["ISBN"]).copy()

    df["ISBN"] = df["ISBN"].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df["ISBN"] = df["ISBN"].str.replace('-', '', regex=False).str.replace(' ', '', regex=False)

    # Nettoyage et conversion des colonnes
    for c in ["Vente", "Retour", "Net", "Facture"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).round(2)

    # Calcul remises libraires
    df["Remise"] = (df["Net"] - df["Facture"]).round(2)
    df["Retour"] = df["Retour"].abs()  # Retours toujours positifs en débit

    # ========== Calcul commissions ==========
    # Distribution
    raw_dist = df["Vente"] * taux_dist
    sum_raw_dist = raw_dist.sum()
    scaled_dist = raw_dist * (total_com_dist / sum_raw_dist)
    cents_floor = np.floor(scaled_dist * 100).astype(int)
    remainders = (scaled_dist * 100) - cents_floor
    diff = int(round(total_com_dist*100)) - cents_floor.sum()
    idx_sorted = np.argsort(-remainders.values)
    adjust = np.zeros(len(df), dtype=int)
    if diff > 0:
        adjust[idx_sorted[:diff]] = 1
    elif diff < 0:
        adjust[idx_sorted[len(df)+diff:]] = -1
    df["Com_dist"] = (cents_floor + adjust)/100

    # Diffusion
    raw_diff = df["Net"] * taux_diff
    sum_raw_diff = raw_diff.sum()
    scaled_diff = raw_diff * (total_com_diff / sum_raw_diff)
    cents_floor = np.floor(scaled_diff * 100).astype(int)
    remainders = (scaled_diff * 100) - cents_floor
    diff = int(round(total_com_diff*100)) - cents_floor.sum()
    idx_sorted = np.argsort(-remainders.values)
    adjust = np.zeros(len(df), dtype=int)
    if diff > 0:
        adjust[idx_sorted[:diff]] = 1
    elif diff < 0:
        adjust[idx_sorted[len(df)+diff:]] = -1
    df["Com_diff"] = (cents_floor + adjust)/100

    # ========== Construction écritures par ISBN ==========
    ecritures = []
    for _, r in df.iterrows():
        # CA brut
        if r["Vente"] != 0:
            ecritures.append({"Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal, "Compte": compte_ca,
                              "Libelle": f"{libelle_base} - CA Brut", "ISBN": r["ISBN"],
                              "Débit": 0.0, "Crédit": r["Vente"]})
        # Retours
        if r["Retour"] != 0:
            ecritures.append({"Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal, "Compte": compte_retour,
                              "Libelle": f"{libelle_base} - Retours", "ISBN": r["ISBN"],
                              "Débit": r["Retour"], "Crédit": 0.0})
        # Remises libraires
        if r["Remise"] != 0:
            ecritures.append({"Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal, "Compte": compte_remise,
                              "Libelle": f"{libelle_base} - Remises libraires", "ISBN": r["ISBN"],
                              "Débit": r["Remise"], "Crédit": 0.0})
        # Commissions distribution
        if r["Com_dist"] != 0:
            ecritures.append({"Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal, "Compte": compte_com_dist,
                              "Libelle": f"{libelle_base} - Commissions distribution", "ISBN": r["ISBN"],
                              "Débit": r["Com_dist"], "Crédit": 0.0})
        # Commissions diffusion
        if r["Com_diff"] != 0:
            ecritures.append({"Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal, "Compte": compte_com_diff,
                              "Libelle": f"{libelle_base} - Commissions diffusion", "ISBN": r["ISBN"],
                              "Débit": r["Com_diff"], "Crédit": 0.0})

    # ========== Écritures globales ==========
    total_net_apres_remise_retour = (df["Facture"] - df["Retour"]).sum().round(2)
    # TVA collectée 5,5%
    tva_collectee = round(total_net_apres_remise_retour * 0.055, 2)
    if tva_collectee !=0:
        ecritures.append({"Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal, "Compte": compte_tva_collectee,
                           "Libelle": f"{libelle_base} - TVA collectée", "ISBN": "",
                           "Débit": 0.0, "Crédit": tva_collectee})
    # TVA déductible sur commissions 5,5%
    tva_deductible = round((df["Com_dist"]+df["Com_diff"]).sum()*0.055,2)
    if tva_deductible !=0:
        ecritures.append({"Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal, "Compte": compte_tva_deductible,
                           "Libelle": f"{libelle_base} - TVA déductible commissions", "ISBN": "",
                           "Débit": tva_deductible, "Crédit": 0.0})
    # Provision retours 10% TTC sur CA brut
    prov_retour = round(df["Vente"].sum() * taux_prov_retour,2)
    if prov_retour !=0:
        ecritures.append({"Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal, "Compte": compte_prov_retour_debit,
                           "Libelle": f"{libelle_base} - Provision retours", "ISBN": "",
                           "Débit": prov_retour, "Crédit": 0.0})
    # Reprise ancienne provision
    if provision_ancienne !=0:
        ecritures.append({"Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal, "Compte": compte_prov_retour_credit,
                           "Libelle": f"{libelle_base} - Reprise provision retours", "ISBN": "",
                           "Débit": 0.0, "Crédit": provision_ancienne})

    df_ecr = pd.DataFrame(ecritures)

    # Tri par ISBN
    df_ecr.sort_values(by="ISBN", inplace=True, kind="mergesort")
    df_ecr.reset_index(drop=True, inplace=True)

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

    st.download_button("📥 Télécharger les écritures (Excel)", data=buffer,
                       file_name="Ecritures_BLDD.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.subheader("👀 Aperçu des écritures générées")
    st.dataframe(df_ecr)
