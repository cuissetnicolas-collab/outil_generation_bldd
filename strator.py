import pandas as pd
import numpy as np
from openpyxl import load_workbook
import streamlit as st
from io import BytesIO

# ===== Interface utilisateur =====
st.title("📊 BLDD Edition - Générateur d'écritures analytiques")

fichier_entree = st.file_uploader("📂 Importer le fichier Excel BLDD", type=["xlsx"])
date_ecriture = st.date_input("📅 Date d'écriture")
journal = st.text_input("📒 Journal", value="VT")
libelle_base = st.text_input("📝 Libellé", value="VENTES BLDD")

# Comptes
compte_ca_brut = st.text_input("💰 Compte CA Brut", value="701100000")
compte_retour = st.text_input("💰 Compte Retours", value="709000000")
compte_remise = st.text_input("💰 Compte Remises libraires", value="709100000")
compte_com_dist = st.text_input("💰 Compte Commissions Distribution", value="622800000")
compte_com_diff = st.text_input("💰 Compte Commissions Diffusion", value="622800010")
compte_tva_collectee = st.text_input("💰 Compte TVA collectée", value="445710060")
compte_tva_deductible = st.text_input("💰 Compte TVA déductible sur commissions", value="445660")
compte_provision_debit = st.text_input("💰 Compte Provision retours (Débit)", value="681000000")
compte_provision_credit = st.text_input("💰 Compte Provision retours (Crédit)", value="151000000")

# 🔹 Saisie des taux
taux_dist = st.number_input("Taux distribution (%)", value=12.5) / 100
taux_diff = st.number_input("Taux diffusion (%)", value=9.0) / 100

# 🔹 Saisie des montants totaux pour équilibre
total_com_dist = st.number_input("Montant total commissions distribution", value=1000.0, format="%.2f")
total_com_diff = st.number_input("Montant total commissions diffusion", value=500.0, format="%.2f")

# 🔹 Provisions
provision_ancienne = st.number_input("Reprise provision 6 mois avant", value=0.0, format="%.2f")

# ===== Traitement =====
if fichier_entree is not None:
    df = pd.read_excel(fichier_entree, header=9, dtype={"ISBN": str})
    df.columns = df.columns.str.strip()
    df = df.dropna(subset=["ISBN"]).copy()

    df["ISBN"] = df["ISBN"].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df["ISBN"] = df["ISBN"].str.replace('-', '', regex=False).str.replace(' ', '', regex=False)

    # Conversion numérique
    for c in ["Vente", "Retour", "Net", "Facture"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).round(2)

    # ===== Commissions distribution =====
    raw_dist = df["Net"] * taux_dist
    sum_raw_dist = raw_dist.sum()
    scaled_dist = raw_dist * (total_com_dist / sum_raw_dist)
    cents_floor = np.floor(scaled_dist * 100).astype(int)
    remainders = (scaled_dist * 100) - cents_floor
    diff = int(round(total_com_dist * 100)) - cents_floor.sum()
    idx_sorted = np.argsort(-remainders.values)
    adjust = np.zeros(len(df), dtype=int)
    if diff > 0:
        adjust[idx_sorted[:diff]] = 1
    elif diff < 0:
        adjust[idx_sorted[len(df)+diff:]] = -1
    df["Commission_distribution"] = (cents_floor + adjust)/100.0

    # ===== Commissions diffusion =====
    raw_diff = df["Net"] * taux_diff
    sum_raw_diff = raw_diff.sum()
    scaled_diff = raw_diff * (total_com_diff / sum_raw_diff)
    cents_floor = np.floor(scaled_diff * 100).astype(int)
    remainders = (scaled_diff * 100) - cents_floor
    diff = int(round(total_com_diff * 100)) - cents_floor.sum()
    idx_sorted = np.argsort(-remainders.values)
    adjust = np.zeros(len(df), dtype=int)
    if diff > 0:
        adjust[idx_sorted[:diff]] = 1
    elif diff < 0:
        adjust[idx_sorted[len(df)+diff:]] = -1
    df["Commission_diffusion"] = (cents_floor + adjust)/100.0

    # ===== Calculs TVA et provision =====
    df["Remise"] = df["Net"] - df["Facture"]
    df["Retour_Pos"] = df["Retour"].abs()
    df["CA_TTC"] = df["Vente"]  # simplifié, TTC = HT * 1.055 si nécessaire
    provision_retour = (df["Vente"].sum() * 1.055) * 0.10  # 10% TTC
    tva_collectee = df["Facture"].sum() * 0.055
    tva_deductible = (df["Commission_distribution"].sum() + df["Commission_diffusion"].sum()) * 0.055

    # ===== Construction écritures =====
    ecritures = []

    for _, r in df.iterrows():
        isbn = r["ISBN"]
        # CA Brut
        ecritures.append({"Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal,
                          "Compte": compte_ca_brut, "Libelle": f"{libelle_base} - CA Brut", "ISBN": isbn,
                          "Débit": 0.0, "Crédit": r["Vente"]})
        # Retours
        ecritures.append({"Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal,
                          "Compte": compte_retour, "Libelle": f"{libelle_base} - Retours", "ISBN": isbn,
                          "Débit": r["Retour_Pos"], "Crédit": 0.0})
        # Remises libraires
        ecritures.append({"Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal,
                          "Compte": compte_remise, "Libelle": f"{libelle_base} - Remises", "ISBN": isbn,
                          "Débit": r["Remise"], "Crédit": 0.0})
        # Commissions distribution
        ecritures.append({"Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal,
                          "Compte": compte_com_dist, "Libelle": f"{libelle_base} - Com Dist", "ISBN": isbn,
                          "Débit": r["Commission_distribution"], "Crédit": 0.0})
        # Commissions diffusion
        ecritures.append({"Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal,
                          "Compte": compte_com_diff, "Libelle": f"{libelle_base} - Com Diff", "ISBN": isbn,
                          "Débit": r["Commission_diffusion"], "Crédit": 0.0})

    # TVA collectée globale
    ecritures.append({"Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal,
                      "Compte": compte_tva_collectee, "Libelle": f"{libelle_base} - TVA Collectée", "ISBN": "",
                      "Débit": 0.0, "Crédit": tva_collectee})
    # TVA déductible sur commissions globale
    ecritures.append({"Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal,
                      "Compte": compte_tva_deductible, "Libelle": f"{libelle_base} - TVA Deductible Com", "ISBN": "",
                      "Débit": tva_deductible, "Crédit": 0.0})
    # Provision retours
    ecritures.append({"Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal,
                      "Compte": compte_provision_debit, "Libelle": f"{libelle_base} - Provision Retours", "ISBN": "",
                      "Débit": provision_retour, "Crédit": 0.0})
    # Reprise ancienne provision
    if provision_ancienne > 0:
        ecritures.append({"Date": date_ecriture.strftime("%d/%m/%Y"), "Journal": journal,
                          "Compte": compte_provision_credit, "Libelle": f"{libelle_base} - Reprise Provision", "ISBN": "",
                          "Débit": 0.0, "Crédit": provision_ancienne})

    df_ecr = pd.DataFrame(ecritures)

    # ===== Vérification équilibre =====
    total_debit = round(df_ecr["Débit"].sum(), 2)
    total_credit = round(df_ecr["Crédit"].sum(), 2)
    if total_debit != total_credit:
        st.error(f"⚠️ Écriture déséquilibrée : Débit={total_debit}, Crédit={total_credit}")
    else:
        st.success("✅ Écritures équilibrées !")

    # ===== Regroupement par ISBN pour vérification =====
    grouped = df_ecr.groupby("ISBN").agg({"Débit":"sum","Crédit":"sum"}).reset_index()
    st.subheader("📊 Vérification par ISBN")
    st.dataframe(grouped)

    # ===== Export Excel =====
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

    # Aperçu complet
    st.subheader("👀 Aperçu des écritures générées")
    st.dataframe(df_ecr)
