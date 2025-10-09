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

# 🔹 Comptes
compte_ca_brut = st.text_input("Compte CA brut", value="701100000")
compte_retour = st.text_input("Compte retours", value="709000000")
compte_remise = st.text_input("Compte remises libraires", value="709100000")
compte_tva = st.text_input("Compte TVA ventes", value="445710060")
compte_provision_debit = st.text_input("Compte provision retours débit", value="681000000")
compte_provision_credit = st.text_input("Compte provision retours crédit", value="151000000")
compte_com_dist = st.text_input("Compte commissions distribution", value="622800000")
compte_com_diff = st.text_input("Compte commissions diffusion", value="622800010")
compte_tva_com = st.text_input("Compte TVA déductible commissions", value="445660000")

# 🔹 Taux et montants
taux_tva = st.number_input("Taux TVA ventes (%)", value=5.5)/100
taux_tva_com = st.number_input("Taux TVA commissions (%)", value=5.5)/100
taux_dist = st.number_input("Taux distribution (%)", value=12.5)/100
taux_diff = st.number_input("Taux diffusion (%)", value=9.0)/100
total_com_dist = st.number_input("Montant total commissions distribution", value=1000.0)
total_com_diff = st.number_input("Montant total commissions diffusion", value=500.0)
provision_ancienne = st.number_input("Reprise provision ancienne (6 mois) ", value=0.0)

# ========== Traitement ==========
if fichier_entree is not None:
    df = pd.read_excel(fichier_entree, header=9, dtype={"ISBN": str})
    df.columns = df.columns.str.strip()
    df = df.dropna(subset=["ISBN"]).copy()

    # Nettoyage ISBN
    df["ISBN"] = df["ISBN"].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df["ISBN"] = df["ISBN"].str.replace('-', '', regex=False).str.replace(' ', '', regex=False)

    # Colonnes numériques
    for c in ["Vente","Retour","Net","Facture"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).round(2)

    # 🔹 Calcul remises libraires
    df["Remise_libraire"] = (df["Net"] - df["Facture"]).round(2)

    # 🔹 Commissions distribution
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
    df["Commission_distribution"] = (cents_floor + adjust)/100.0

    # 🔹 Commissions diffusion
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
    df["Commission_diffusion"] = (cents_floor + adjust)/100.0

    # 🔹 Provisions retours (10% TTC sur Vente)
    df["Provision_retour"] = (df["Vente"]*1.055*0.10).round(2)  # TTC approximé

    # ========== Construction écritures ==========
    ecritures = []

    # CA brut
    for _, r in df.iterrows():
        if r["Vente"]>0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"),
                "Journal": journal,
                "Compte": compte_ca_brut,
                "Libelle": f"{libelle_base} - CA brut",
                "ISBN": r["ISBN"],
                "Débit": 0.0,
                "Crédit": r["Vente"]
            })

    # Retours
    for _, r in df.iterrows():
        if r["Retour"]>0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"),
                "Journal": journal,
                "Compte": compte_retour,
                "Libelle": f"{libelle_base} - Retours",
                "ISBN": r["ISBN"],
                "Débit": r["Retour"],
                "Crédit": 0.0
            })

    # Remises libraires
    for _, r in df.iterrows():
        if r["Remise_libraire"]>0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"),
                "Journal": journal,
                "Compte": compte_remise,
                "Libelle": f"{libelle_base} - Remise libraire",
                "ISBN": r["ISBN"],
                "Débit": r["Remise_libraire"],
                "Crédit": 0.0
            })

    # TVA ventes (sur Net après remises et retours)
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

    # Commissions distribution
    for _, r in df.iterrows():
        if r["Commission_distribution"]>0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"),
                "Journal": journal,
                "Compte": compte_com_dist,
                "Libelle": f"{libelle_base} - Com distribution",
                "ISBN": r["ISBN"],
                "Débit": r["Commission_distribution"],
                "Crédit": 0.0
            })
            # TVA déductible
            tva_com = (r["Commission_distribution"]*taux_tva_com).round(2)
            if tva_com>0:
                ecritures.append({
                    "Date": date_ecriture.strftime("%d/%m/%Y"),
                    "Journal": journal,
                    "Compte": compte_tva_com,
                    "Libelle": f"{libelle_base} - TVA distribution",
                    "ISBN": "",
                    "Débit": 0.0,
                    "Crédit": tva_com
                })

    # Commissions diffusion
    for _, r in df.iterrows():
        if r["Commission_diffusion"]>0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"),
                "Journal": journal,
                "Compte": compte_com_diff,
                "Libelle": f"{libelle_base} - Com diffusion",
                "ISBN": r["ISBN"],
                "Débit": r["Commission_diffusion"],
                "Crédit": 0.0
            })
            # TVA déductible
            tva_com = (r["Commission_diffusion"]*taux_tva_com).round(2)
            if tva_com>0:
                ecritures.append({
                    "Date": date_ecriture.strftime("%d/%m/%Y"),
                    "Journal": journal,
                    "Compte": compte_tva_com,
                    "Libelle": f"{libelle_base} - TVA diffusion",
                    "ISBN": "",
                    "Débit": 0.0,
                    "Crédit": tva_com
                })

    # Provisions retours
    total_provision = df["Provision_retour"].sum().round(2)
    if total_provision>0:
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_provision_debit,
            "Libelle": f"{libelle_base} - Provision retours",
            "ISBN": "",
            "Débit": total_provision,
            "Crédit": 0.0
        })
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_provision_credit,
            "Libelle": f"{libelle_base} - Provision retours",
            "ISBN": "",
            "Débit": 0.0,
            "Crédit": total_provision
        })

    # Reprise provision ancienne
    if provision_ancienne>0:
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_provision_debit,
            "Libelle": f"{libelle_base} - Reprise provision ancienne",
            "ISBN": "",
            "Débit": 0.0,
            "Crédit": provision_ancienne
        })
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_provision_credit,
            "Libelle": f"{libelle_base} - Reprise provision ancienne",
            "ISBN": "",
            "Débit": provision_ancienne,
            "Crédit": 0.0
        })

    df_ecr = pd.DataFrame(ecritures)

    # Vérification équilibre
    total_debit = round(df_ecr["Débit"].sum(),2)
    total_credit = round(df_ecr["Crédit"].sum(),2)
    if total_debit != total_credit:
        st.error(f"⚠️ Écritures déséquilibrées : Débit={total_debit}, Crédit={total_credit}")
    else:
        st.success("✅ Écritures équilibrées !")

    # ========== Export ==========
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
    st.subheader("👀 Aperçu des écritures")
    st.dataframe(df_ecr)
