import pandas as pd
import numpy as np
from io import BytesIO
import streamlit as st

# ========== Interface utilisateur ==========
st.title("📊 Générateur d'écritures analytiques - BLDD Edition")

fichier_entree = st.file_uploader("📂 Importer le fichier Excel BLDD", type=["xlsx"])
date_ecriture = st.date_input("📅 Date d'écriture")
journal = st.text_input("📒 Journal", value="VT")
libelle_base = st.text_input("📝 Libellé", value="VENTES BLDD")

# Comptes
compte_ca_brut = st.text_input("💰 Compte CA Brut", value="701100000")
compte_retour = st.text_input("💰 Compte Retours", value="709000000")
compte_remise = st.text_input("💰 Compte Remises libraires", value="709100000")
compte_com_dist = st.text_input("💰 Compte Commissions distribution", value="622800000")
compte_com_diff = st.text_input("💰 Compte Commissions diffusion", value="622800010")
compte_tva_ventes = st.text_input("💰 Compte TVA collectée", value="445710060")
compte_tva_comm = st.text_input("💰 Compte TVA déductible sur commissions", value="445660")
compte_provision_retour_debit = st.text_input("💰 Compte Provision retours (Débit)", value="681")
compte_provision_retour_credit = st.text_input("💰 Compte Provision retours (Crédit)", value="151")

# Taux et montants
taux_dist = st.number_input("Taux distribution (%)", value=12.5)/100
taux_diff = st.number_input("Taux diffusion (%)", value=9.0)/100
tva_ventes = st.number_input("TVA sur ventes (%)", value=5.5)/100
tva_comm = st.number_input("TVA sur commissions (%)", value=5.5)/100
montant_com_dist_total = st.number_input("Montant total commissions distribution", value=1000.0, format="%.2f")
montant_com_diff_total = st.number_input("Montant total commissions diffusion", value=500.0, format="%.2f")
montant_reprise_provision = st.number_input("Montant reprise provision ancienne", value=0.0, format="%.2f")

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

    # Calcul remises libraires
    df["Remise"] = df["Net"] - df["Facture"]

    # ========== Commissions distribution ==========
    raw_dist = df["Net"] * taux_dist
    sum_raw_dist = raw_dist.sum()
    scaled_dist = raw_dist * (montant_com_dist_total / sum_raw_dist)
    cents_floor = np.floor(scaled_dist * 100).astype(int)
    remainders = (scaled_dist * 100) - cents_floor
    diff = int(round(montant_com_dist_total*100)) - cents_floor.sum()
    idx_sorted = np.argsort(-remainders.values)
    adjust = np.zeros(len(df), dtype=int)
    if diff > 0:
        adjust[idx_sorted[:diff]] = 1
    elif diff < 0:
        adjust[idx_sorted[len(df)+diff:]] = -1
    df["Commission_distribution"] = (cents_floor + adjust)/100.0

    # ========== Commissions diffusion ==========
    raw_diff = df["Net"] * taux_diff
    sum_raw_diff = raw_diff.sum()
    scaled_diff = raw_diff * (montant_com_diff_total / sum_raw_diff)
    cents_floor = np.floor(scaled_diff * 100).astype(int)
    remainders = (scaled_diff * 100) - cents_floor
    diff = int(round(montant_com_diff_total*100)) - cents_floor.sum()
    idx_sorted = np.argsort(-remainders.values)
    adjust = np.zeros(len(df), dtype=int)
    if diff > 0:
        adjust[idx_sorted[:diff]] = 1
    elif diff < 0:
        adjust[idx_sorted[len(df)+diff:]] = -1
    df["Commission_diffusion"] = (cents_floor + adjust)/100.0

    # ========== Écritures ==========
    ecritures = []

    # Boucle par ISBN
    for _, r in df.iterrows():
        isbn = r["ISBN"]

        # CA Brut (Vente)
        if r["Vente"] != 0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"),
                "Journal": journal,
                "Compte": compte_ca_brut,
                "Libelle": f"{libelle_base} - CA Brut",
                "ISBN": isbn,
                "Débit": 0.0,
                "Crédit": r["Vente"]
            })

        # Retours (positif au débit)
        if r["Retour"] != 0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"),
                "Journal": journal,
                "Compte": compte_retour,
                "Libelle": f"{libelle_base} - Retours",
                "ISBN": isbn,
                "Débit": abs(r["Retour"]),
                "Crédit": 0.0
            })

        # Remises libraires
        if r["Remise"] != 0:
            debit, credit = (0.0, abs(r["Remise"])) if r["Remise"] < 0 else (abs(r["Remise"]), 0.0)
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"),
                "Journal": journal,
                "Compte": compte_remise,
                "Libelle": f"{libelle_base} - Remises libraires",
                "ISBN": isbn,
                "Débit": debit,
                "Crédit": credit
            })

        # Commissions distribution
        if r["Commission_distribution"] != 0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"),
                "Journal": journal,
                "Compte": compte_com_dist,
                "Libelle": f"{libelle_base} - Com. distribution",
                "ISBN": isbn,
                "Débit": r["Commission_distribution"],
                "Crédit": 0.0
            })

        # Commissions diffusion
        if r["Commission_diffusion"] != 0:
            ecritures.append({
                "Date": date_ecriture.strftime("%d/%m/%Y"),
                "Journal": journal,
                "Compte": compte_com_diff,
                "Libelle": f"{libelle_base} - Com. diffusion",
                "ISBN": isbn,
                "Débit": r["Commission_diffusion"],
                "Crédit": 0.0
            })

    # ========== TVA ==========

    ca_net = (df["Facture"].sum()).round(2)
    tva_ventes_montant = round(ca_net * tva_ventes,2)
    tva_comm_montant = round((df["Commission_distribution"].sum() + df["Commission_diffusion"].sum()) * tva_comm,2)

    # TVA collectée
    ecritures.append({
        "Date": date_ecriture.strftime("%d/%m/%Y"),
        "Journal": journal,
        "Compte": compte_tva_ventes,
        "Libelle": f"{libelle_base} - TVA collectée",
        "ISBN": "",
        "Débit": 0.0,
        "Crédit": tva_ventes_montant
    })

    # TVA déductible sur commissions
    ecritures.append({
        "Date": date_ecriture.strftime("%d/%m/%Y"),
        "Journal": journal,
        "Compte": compte_tva_comm,
        "Libelle": f"{libelle_base} - TVA sur commissions",
        "ISBN": "",
        "Débit": tva_comm_montant,
        "Crédit": 0.0
    })

    # Provisions retours
    provision_retour = round(df["Vente"].sum() * 1.055 * 0.10,2)  # TTC brut 10%
    ecritures.append({
        "Date": date_ecriture.strftime("%d/%m/%Y"),
        "Journal": journal,
        "Compte": compte_provision_retour_debit,
        "Libelle": f"{libelle_base} - Provision retours",
        "ISBN": "",
        "Débit": provision_retour,
        "Crédit": 0.0
    })
    # Reprise ancienne provision
    if montant_reprise_provision != 0:
        ecritures.append({
            "Date": date_ecriture.strftime("%d/%m/%Y"),
            "Journal": journal,
            "Compte": compte_provision_retour_credit,
            "Libelle": f"{libelle_base} - Reprise provision ancienne",
            "ISBN": "",
            "Débit": 0.0,
            "Crédit": montant_reprise_provision
        })

    df_ecr = pd.DataFrame(ecritures)

    # Vérification équilibre
    total_debit = round(df_ecr["Débit"].sum(),2)
    total_credit = round(df_ecr["Crédit"].sum(),2)
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
