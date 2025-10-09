import pandas as pd
import numpy as np
from io import BytesIO
import streamlit as st
from datetime import datetime

st.set_page_config(page_title="BLDD Générateur d'écritures", layout="wide")
st.title("📊 Générateur d'écritures BLDD - Version Analytique")

# ===== Import fichier =====
fichier = st.file_uploader("📂 Importer le fichier Excel BLDD", type=["xlsx"])
date_ecriture = st.date_input("📅 Date d'écriture", value=datetime.today())
journal = st.text_input("📒 Journal", value="VT")
libelle_base = st.text_input("📝 Libellé", value="VENTES BLDD")

# ===== Comptes =====
compte_ca_brut = st.text_input("💰 Compte CA Brut", value="701100000")
compte_retour = st.text_input("💰 Compte Retours", value="709000000")
compte_remise = st.text_input("💰 Compte Remises Libraires", value="709100000")
compte_com_dist = st.text_input("💰 Compte Commissions Distribution", value="622800000")
compte_com_diff = st.text_input("💰 Compte Commissions Diffusion", value="622800010")
compte_client = st.text_input("💰 Compte Client", value="411100011")
compte_tva_col = st.text_input("💰 TVA Collectée", value="445710060")
compte_tva_dist_diff = st.text_input("💰 TVA Déductible sur commissions", value="445660")
compte_prov_retour_debit = st.text_input("💰 Provision Retours (Débit)", value="681000000")
compte_prov_retour_credit = st.text_input("💰 Provision Retours (Crédit)", value="151000000")

# ===== Taux et montants =====
taux_dist = st.number_input("Taux distribution (%)", value=12.5)/100
taux_diff = st.number_input("Taux diffusion (%)", value=9.0)/100
tva = 0.055

montant_com_dist_total = st.number_input("Montant total commissions distribution", value=1000.0, format="%.2f")
montant_com_diff_total = st.number_input("Montant total commissions diffusion", value=500.0, format="%.2f")
prov_reprise = st.number_input("Reprise ancienne provision (6 mois)", value=0.0, format="%.2f")

if fichier is not None:
    df = pd.read_excel(fichier, header=9, dtype={"ISBN": str})
    df.columns = df.columns.str.strip()
    df = df.dropna(subset=["ISBN"]).copy()
    
    # Nettoyage ISBN
    df["ISBN"] = df["ISBN"].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    df["ISBN"] = df["ISBN"].str.replace('-', '', regex=False).str.replace(' ', '', regex=False)

    # Colonnes numériques
    for c in ["Vente","Retour","Net","Facture"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).round(2)

    # ===== Commissions =====
    # Distribution
    raw_dist = df["Vente"] * taux_dist
    sum_raw_dist = raw_dist.sum()
    scaled_dist = raw_dist * (montant_com_dist_total / sum_raw_dist)
    cents_floor = np.floor(scaled_dist*100).astype(int)
    remainders = (scaled_dist*100) - cents_floor
    diff = int(round(montant_com_dist_total*100)) - cents_floor.sum()
    idx_sorted = np.argsort(-remainders.values)
    adjust = np.zeros(len(df), dtype=int)
    if diff>0:
        adjust[idx_sorted[:diff]]=1
    elif diff<0:
        adjust[idx_sorted[len(df)+diff:]]=-1
    df["Commission_distribution"] = (cents_floor + adjust)/100.0

    # Diffusion
    raw_diff = df["Net"] * taux_diff
    sum_raw_diff = raw_diff.sum()
    scaled_diff = raw_diff * (montant_com_diff_total / sum_raw_diff)
    cents_floor = np.floor(scaled_diff*100).astype(int)
    remainders = (scaled_diff*100) - cents_floor
    diff = int(round(montant_com_diff_total*100)) - cents_floor.sum()
    idx_sorted = np.argsort(-remainders.values)
    adjust = np.zeros(len(df), dtype=int)
    if diff>0:
        adjust[idx_sorted[:diff]]=1
    elif diff<0:
        adjust[idx_sorted[len(df)+diff:]]=-1
    df["Commission_diffusion"] = (cents_floor + adjust)/100.0

    # ===== Écritures =====
    ecritures=[]
    
    for _, r in df.iterrows():
        # CA brut
        ecritures.append({"Date":date_ecriture.strftime("%d/%m/%Y"),
                          "Journal":journal, "Compte":compte_ca_brut,
                          "Libelle":f"{libelle_base} - CA Brut", "ISBN":r["ISBN"],
                          "Débit":0.0, "Crédit":r["Vente"]})
        ecritures.append({"Date":date_ecriture.strftime("%d/%m/%Y"),
                          "Journal":journal, "Compte":compte_client,
                          "Libelle":f"{libelle_base} - CA Brut", "ISBN":r["ISBN"],
                          "Débit":r["Vente"], "Crédit":0.0})

        # Retours
        retour_pos = abs(r["Retour"])
        ecritures.append({"Date":date_ecriture.strftime("%d/%m/%Y"),
                          "Journal":journal, "Compte":compte_retour,
                          "Libelle":f"{libelle_base} - Retours", "ISBN":r["ISBN"],
                          "Débit":retour_pos, "Crédit":0.0})
        ecritures.append({"Date":date_ecriture.strftime("%d/%m/%Y"),
                          "Journal":journal, "Compte":compte_client,
                          "Libelle":f"{libelle_base} - Retours", "ISBN":r["ISBN"],
                          "Débit":0.0, "Crédit":retour_pos})

        # Remises libraires
        remise = r["Net"] - r["Facture"]
        if remise>=0:
            ecritures.append({"Date":date_ecriture.strftime("%d/%m/%Y"),
                              "Journal":journal, "Compte":compte_remise,
                              "Libelle":f"{libelle_base} - Remises Libraires", "ISBN":r["ISBN"],
                              "Débit":remise, "Crédit":0.0})
            ecritures.append({"Date":date_ecriture.strftime("%d/%m/%Y"),
                              "Journal":journal, "Compte":compte_client,
                              "Libelle":f"{libelle_base} - Remises Libraires", "ISBN":r["ISBN"],
                              "Débit":0.0, "Crédit":remise})
        else:
            # négatif au crédit
            ecritures.append({"Date":date_ecriture.strftime("%d/%m/%Y"),
                              "Journal":journal, "Compte":compte_remise,
                              "Libelle":f"{libelle_base} - Remises Libraires", "ISBN":r["ISBN"],
                              "Débit":0.0, "Crédit":abs(remise)})
            ecritures.append({"Date":date_ecriture.strftime("%d/%m/%Y"),
                              "Journal":journal, "Compte":compte_client,
                              "Libelle":f"{libelle_base} - Remises Libraires", "ISBN":r["ISBN"],
                              "Débit":abs(remise), "Crédit":0.0})

        # Commissions distribution
        com_dist = r["Commission_distribution"]
        if com_dist>=0:
            ecritures.append({"Date":date_ecriture.strftime("%d/%m/%Y"),
                              "Journal":journal, "Compte":compte_com_dist,
                              "Libelle":f"{libelle_base} - Com Dist", "ISBN":r["ISBN"],
                              "Débit":com_dist, "Crédit":0.0})
            ecritures.append({"Date":date_ecriture.strftime("%d/%m/%Y"),
                              "Journal":journal, "Compte":compte_client,
                              "Libelle":f"{libelle_base} - Com Dist", "ISBN":r["ISBN"],
                              "Débit":0.0, "Crédit":com_dist})
        else:
            # négatif au crédit
            ecritures.append({"Date":date_ecriture.strftime("%d/%m/%Y"),
                              "Journal":journal, "Compte":compte_com_dist,
                              "Libelle":f"{libelle_base} - Com Dist", "ISBN":r["ISBN"],
                              "Débit":0.0, "Crédit":abs(com_dist)})
            ecritures.append({"Date":date_ecriture.strftime("%d/%m/%Y"),
                              "Journal":journal, "Compte":compte_client,
                              "Libelle":f"{libelle_base} - Com Dist", "ISBN":r["ISBN"],
                              "Débit":abs(com_dist), "Crédit":0.0})

        # Commissions diffusion
        com_diff = r["Commission_diffusion"]
        if com_diff>=0:
            ecritures.append({"Date":date_ecriture.strftime("%d/%m/%Y"),
                              "Journal":journal, "Compte":compte_com_diff,
                              "Libelle":f"{libelle_base} - Com Diff", "ISBN":r["ISBN"],
                              "Débit":com_diff, "Crédit":0.0})
            ecritures.append({"Date":date_ecriture.strftime("%d/%m/%Y"),
                              "Journal":journal, "Compte":compte_client,
                              "Libelle":f"{libelle_base} - Com Diff", "ISBN":r["ISBN"],
                              "Débit":0.0, "Crédit":com_diff})
        else:
            ecritures.append({"Date":date_ecriture.strftime("%d/%m/%Y"),
                              "Journal":journal, "Compte":compte_com_diff,
                              "Libelle":f"{libelle_base} - Com Diff", "ISBN":r["ISBN"],
                              "Débit":0.0, "Crédit":abs(com_diff)})
            ecritures.append({"Date":date_ecriture.strftime("%d/%m/%Y"),
                              "Journal":journal, "Compte":compte_client,
                              "Libelle":f"{libelle_base} - Com Diff", "ISBN":r["ISBN"],
                              "Débit":abs(com_diff), "Crédit":0.0})

    # ===== TVA =====
    ca_net_total = df["Facture"].sum()
    tva_collectee = round(ca_net_total * tva,2)
    ecritures.append({"Date":date_ecriture.strftime("%d/%m/%Y"), "Journal":journal,
                      "Compte":compte_tva_col, "Libelle":f"{libelle_base} - TVA Collectée",
                      "ISBN":"", "Débit":0.0, "Crédit":tva_collectee})
    ecritures.append({"Date":date_ecriture.strftime("%d/%m/%Y"), "Journal":journal,
                      "Compte":compte_client, "Libelle":f"{libelle_base} - TVA Collectée",
                      "ISBN":"", "Débit":tva_collectee, "Crédit":0.0})

    # TVA déductible sur commissions
    tva_dist_diff = round((df["Commission_distribution"].sum() + df["Commission_diffusion"].sum())*tva,2)
    ecritures.append({"Date":date_ecriture.strftime("%d/%m/%Y"), "Journal":journal,
                      "Compte":compte_tva_dist_diff, "Libelle":f"{libelle_base} - TVA Déductible Commissions",
                      "ISBN":"", "Débit":tva_dist_diff, "Crédit":0.0})
    ecritures.append({"Date":date_ecriture.strftime("%d/%m/%Y"), "Journal":journal,
                      "Compte":compte_client, "Libelle":f"{libelle_base} - TVA Déductible Commissions",
                      "ISBN":"", "Débit":0.0, "Crédit":tva_dist_diff})

    # Provision retours
    prov = round(df["Vente"].sum()*1.055*0.10,2)  # TTC
    ecritures.append({"Date":date_ecriture.strftime("%d/%m/%Y"), "Journal":journal,
                      "Compte":compte_prov_retour_debit, "Libelle":f"{libelle_base} - Provision Retours",
                      "ISBN":"", "Débit":prov, "Crédit":0.0})
    ecritures.append({"Date":date_ecriture.strftime("%d/%m/%Y"), "Journal":journal,
                      "Compte":compte_prov_retour_credit, "Libelle":f"{libelle_base} - Provision Retours",
                      "ISBN":"", "Débit":0.0, "Crédit":prov})
    # Reprise ancienne provision
    if prov_reprise>0:
        ecritures.append({"Date":date_ecriture.strftime("%d/%m/%Y"), "Journal":journal,
                          "Compte":compte_prov_retour_debit, "Libelle":f"{libelle_base} - Reprise Provision Ancienne",
                          "ISBN":"", "Débit":0.0, "Crédit":prov_reprise})
        ecritures.append({"Date":date_ecriture.strftime("%d/%m/%Y"), "Journal":journal,
                          "Compte":compte_prov_retour_credit, "Libelle":f"{libelle_base} - Reprise Provision Ancienne",
                          "ISBN":"", "Débit":prov_reprise, "Crédit":0.0})

    df_ecr = pd.DataFrame(ecritures)

    st.subheader("👀 Aperçu des écritures générées")
    st.dataframe(df_ecr)

    # Export Excel
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_ecr.to_excel(writer, index=False, sheet_name="Ecritures")
    buffer.seek(0)
    st.download_button("📥 Télécharger les écritures (Excel)", data=buffer,
                       file_name="Ecritures_BLDD.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
