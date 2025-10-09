import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

# =====================
# Interface utilisateur
# =====================
st.title("📊 Générateur d'écriture globale - BLDD")

fichier_bldd = st.file_uploader("📂 Importer le fichier BLDD", type=["xlsx"])
date_ecriture = st.date_input("📅 Date d'écriture")
journal = st.text_input("📒 Journal", value="VT")
libelle_base = st.text_input("📝 Libellé", value="VENTES BLDD")

compte_ca = st.text_input("💰 Compte CA", value="70110000")
compte_tva = st.text_input("💰 Compte TVA collectée", value="44571000")
compte_provision = st.text_input("💰 Compte provision retours", value="41900000")
compte_com_dist = st.text_input("💰 Compte commissions distribution", value="62280000")
compte_com_diff = st.text_input("💰 Compte commissions diffusion", value="62280001")

taux_tva = st.number_input("TVA (%)", value=5.5) / 100
taux_provision = st.number_input("Provision retours (%)", value=10.0) / 100
taux_dist = st.number_input("Distribution (%)", value=12.5) / 100
taux_diff = st.number_input("Diffusion (%)", value=9.0) / 100

if fichier_bldd is not None:
    # ========== Lecture et nettoyage ==========
    df = pd.read_excel(fichier_bldd, header=9, dtype={"ISBN": str})
    df.columns = df.columns.str.strip()
    df = df.dropna(subset=["ISBN"])
    
    # Nettoyage ISBN
    df["ISBN"] = df["ISBN"].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df["ISBN"] = df["ISBN"].str.replace('-', '', regex=False).str.replace(' ', '', regex=False)
    
    # Conversion des colonnes en numérique
    for c in ["Ventes","Retours","Vente","Retour","Net","Facture"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).round(2)
    
    # ========== Calculs ==========
    # CA brut TTC pour provision
    ca_brut_ttc = df["Vente"].sum()
    provision_retours = ca_brut_ttc * taux_provision
    
    # CA HT = Net / (1 + TVA)
    net_ht = df["Net"].sum() / (1 + taux_tva)
    tva_collectee = df["Net"].sum() - net_ht

    # Commissions
    raw_dist = df["Vente"] * taux_dist
    raw_diff = df["Net"] * taux_diff
    total_com_dist = raw_dist.sum()
    total_com_diff = raw_diff.sum()

    # ========== Construction de l'écriture ==========
    ecritures = []

    # CA HT
    ecritures.append({
        "Date": date_ecriture.strftime("%d/%m/%Y"),
        "Journal": journal,
        "Compte": compte_ca,
        "Libelle": f"{libelle_base} - CA HT",
        "Débit": 0.0,
        "Crédit": round(net_ht, 2)
    })

    # TVA
    ecritures.append({
        "Date": date_ecriture.strftime("%d/%m/%Y"),
        "Journal": journal,
        "Compte": compte_tva,
        "Libelle": f"{libelle_base} - TVA collectée",
        "Débit": 0.0,
        "Crédit": round(tva_collectee, 2)
    })

    # Provision retours
    ecritures.append({
        "Date": date_ecriture.strftime("%d/%m/%Y"),
        "Journal": journal,
        "Compte": compte_provision,
        "Libelle": f"{libelle_base} - Provision retours",
        "Débit": 0.0,
        "Crédit": round(provision_retours, 2)
    })

    # Commissions distribution
    ecritures.append({
        "Date": date_ecriture.strftime("%d/%m/%Y"),
        "Journal": journal,
        "Compte": compte_com_dist,
        "Libelle": f"{libelle_base} - Commissions distribution",
        "Débit": round(total_com_dist, 2),
        "Crédit": 0.0
    })

    # Commissions diffusion
    ecritures.append({
        "Date": date_ecriture.strftime("%d/%m/%Y"),
        "Journal": journal,
        "Compte": compte_com_diff,
        "Libelle": f"{libelle_base} - Commissions diffusion",
        "Débit": round(total_com_diff, 2),
        "Crédit": 0.0
    })

    df_ecr = pd.DataFrame(ecritures)

    # Vérification équilibre
    total_debit = df_ecr["Débit"].sum()
    total_credit = df_ecr["Crédit"].sum()
    if round(total_debit,2) != round(total_credit,2):
        st.error(f"⚠️ Écriture déséquilibrée : Débit={total_debit}, Crédit={total_credit}")
    else:
        st.success("✅ Écriture équilibrée et prête à l'import comptable !")

    # Export Excel
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_ecr.to_excel(writer, index=False, sheet_name="Ecriture_BLDD")
    buffer.seek(0)
    st.download_button(
        "📥 Télécharger l'écriture globale (Excel)",
        data=buffer,
        file_name="Ecriture_BLDD.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # Aperçu
    st.subheader("👀 Aperçu de l'écriture générée")
    st.dataframe(df_ecr)
