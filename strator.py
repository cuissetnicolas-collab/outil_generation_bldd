import pandas as pd
import numpy as np
from openpyxl import load_workbook
import streamlit as st
from io import BytesIO

# ========== Interface utilisateur ==========
st.title("📊 Générateur d'écritures analytiques - BLDD")

# 🔹 Import fichier BLDD
fichier_entree = st.file_uploader("📂 Importer le fichier Excel BLDD", type=["xlsx"])
date_ecriture = st.date_input("📅 Date d'écriture")
journal = st.text_input("📒 Journal", value="VT")
libelle_base = st.text_input("📝 Libellé", value="VENTES BLDD")

# 🔹 Comptes comptables
compte_ca = st.text_input("💰 Compte CA brut", value="701100000")
compte_retour = st.text_input("💰 Compte retours", value="709000000")
compte_remise = st.text_input("💰 Compte remises libraires", value="709100000")
compte_tva = st.text_input("💰 Compte TVA collectée", value="445710060")
compte_com_dist = st.text_input("💰 Compte commissions distribution", value="622800000")
compte_com_diff = st.text_input("💰 Compte commissions diffusion", value="622800010")
compte_tva_com = st.text_input("💰 Compte TVA déductible sur commissions", value="445660")
compte_prov_retour_debit = st.text_input("💰 Compte provision retours débit", value="681")
compte_prov_retour_credit = st.text_input("💰 Compte provision retours crédit", value="151")

# 🔹 Taux et montants
taux_dist = st.number_input("Taux distribution (%)", value=12.5)/100
taux_diff = st.number_input("Taux diffusion (%)", value=9.0)/100
taux_tva = 5.5/100
taux_tva_com = 5.5/100

total_com_dist = st.number_input("Montant total commissions distribution", value=1000.0)
total_com_diff = st.number_input("Montant total commissions diffusion", value=500.0)
provision_ancienne = st.number_input("Reprise provision ancienne", value=0.0)

# ========== Traitement ==========
if fichier_entree is not None:
    df = pd.read_excel(fichier_entree, header=9, dtype={"ISBN": str})
    df.columns = df.columns.str.strip()
    df = df.dropna(subset=["ISBN"]).copy()

    # Nettoyage ISBN
    df["ISBN"] = df["ISBN"].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df["ISBN"] = df["ISBN"].str.replace('-', '', regex=False).str.replace(' ', '', regex=False)

    # Conversion des colonnes numériques
    for c in ["Vente", "Retour", "Net", "Facture"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).round(2)

    # Calcul remise libraire
    df["Remise_libraire"] = (df["Net"] - df["Facture"]).clip(lower=0)

    # ========== Calcul commissions distribution ==========
    raw_dist = df["Vente"] * taux_dist
    sum_raw_dist = raw_dist.sum()
    scaled_dist = raw_dist * (total_com_dist / sum_raw_dist)
    cents_floor = np.floor(scaled_dist * 100).astype(int)
    remainders = (scaled_dist * 100) - cents_floor
    diff = int(round(total_com_dist*100)) - cents_floor.sum()
    idx_sorted = np.argsort(-remainders.values)
    adjust = np.zeros(len(df), dtype=int)
    if diff>0:
        adjust[idx_sorted[:diff]] = 1
    elif diff<0:
        adjust[idx_sorted[len(df)+diff:]] = -1
    df["Commission_distribution"] = (cents_floor + adjust)/100.0

    # ========== Calcul commissions diffusion ==========
    raw_diff = df["Net"] * taux_diff
    sum_raw_diff = raw_diff.sum()
    scaled_diff = raw_diff * (total_com_diff / sum_raw_diff)
    cents_floor = np.floor(scaled_diff * 100).astype(int)
    remainders = (scaled_diff * 100) - cents_floor
    diff = int(round(total_com_diff*100)) - cents_floor.sum()
    idx_sorted = np.argsort(-remainders.values)
    adjust = np.zeros(len(df), dtype=int)
    if diff>0:
        adjust[idx_sorted[:diff]] = 1
    elif diff<0:
        adjust[idx_sorted[len(df)+diff:]] = -1
    df["Commission_diffusion"] = (cents_floor + adjust)/100.0

    # ========== Construction écritures ==========
    ecritures = []

    # 🔹 Ventes brutes
    for _, r in df.iterrows():
        if r["Vente"]>0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"),
                "Journal": journal,
                "Compte": compte_ca,
                "Libelle": f"{libelle_base} - CA brut",
                "ISBN": r["ISBN"],
                "Débit": 0.0,
                "Crédit": r["Vente"]
            })

    # 🔹 Retours
    for _, r in df.iterrows():
        if r["Retour"] !=0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"),
                "Journal": journal,
                "Compte": compte_retour,
                "Libelle": f"{libelle_base} - Retours",
                "ISBN": r["ISBN"],
                "Débit": abs(r["Retour"]),
                "Crédit": 0.0
            })

    # 🔹 Remises libraires
    for _, r in df.iterrows():
        if r["Remise_libraire"]>0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"),
                "Journal": journal,
                "Compte": compte_remise,
                "Libelle": f"{libelle_base} - Remises libraires",
                "ISBN": r["ISBN"],
                "Débit": r["Remise_libraire"],
                "Crédit": 0.0
            })

    # 🔹 TVA collectée sur CA net après remise et retours
    df["CA_net_apres"] = (df["Net"] - df["Remise_libraire"] - df["Retour"]).clip(lower=0)
    total_tva = (df["CA_net_apres"]*taux_tva).sum().round(2)
    if total_tva>0:
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_tva,
            "Libelle": f"{libelle_base} - TVA ventes",
            "ISBN": "",
            "Débit": 0.0,
            "Crédit": total_tva
        })

    # 🔹 Commissions distribution et diffusion
    for _, r in df.iterrows():
        if r["Commission_distribution"]>0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"),
                "Journal": journal,
                "Compte": compte_com_dist,
                "Libelle": f"{libelle_base} - Commission distribution",
                "ISBN": r["ISBN"],
                "Débit": round(r["Commission_distribution"],2),
                "Crédit": 0.0
            })
        if r["Commission_diffusion"]>0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"),
                "Journal": journal,
                "Compte": compte_com_diff,
                "Libelle": f"{libelle_base} - Commission diffusion",
                "ISBN": r["ISBN"],
                "Débit": round(r["Commission_diffusion"],2),
                "Crédit": 0.0
            })

    # 🔹 TVA déductible sur commissions (au débit)
    for _, r in df.iterrows():
        tva_com_dist = round(r["Commission_distribution"]*taux_tva_com,2)
        tva_com_diff = round(r["Commission_diffusion"]*taux_tva_com,2)
        if tva_com_dist>0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"),
                "Journal": journal,
                "Compte": compte_tva_com,
                "Libelle": f"{libelle_base} - TVA distribution",
                "ISBN": "",
                "Débit": tva_com_dist,
                "Crédit": 0.0
            })
        if tva_com_diff>0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"),
                "Journal": journal,
                "Compte": compte_tva_com,
                "Libelle": f"{libelle_base} - TVA diffusion",
                "ISBN": "",
                "Débit": tva_com_diff,
                "Crédit": 0.0
            })

    # 🔹 Provisions retours
    prov_retour = (df["Vente"]*1.055*0.10).sum().round(2)  # 10% TTC sur CA brut
    if prov_retour>0:
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_prov_retour_debit,
            "Libelle": f"{libelle_base} - Provision retours",
            "ISBN": "",
            "Débit": prov_retour,
            "Crédit": 0.0
        })
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_prov_retour_credit,
            "Libelle": f"{libelle_base} - Provision retours",
            "ISBN": "",
            "Débit": 0.0,
            "Crédit": prov_retour
        })

    # 🔹 Reprise ancienne provision
    if provision_ancienne>0:
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_prov_retour_debit,
            "Libelle": f"{libelle_base} - Reprise provision",
            "ISBN": "",
            "Débit": 0.0,
            "Crédit": provision_ancienne
        })
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_prov_retour_credit,
            "Libelle": f"{libelle_base} - Reprise provision",
            "ISBN": "",
            "Débit": provision_ancienne,
            "Crédit": 0.0
        })

    # 🔹 Création DataFrame final
    df_ecr = pd.DataFrame(ecritures)

    # 🔹 Vérification équilibre
    total_debit = round(df_ecr["Débit"].sum(),2)
    total_credit = round(df_ecr["Crédit"].sum(),2)
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

    # Aperçu dans l’appli
    st.subheader("👀 Aperçu des écritures générées")
    st.dataframe(df_ecr)
