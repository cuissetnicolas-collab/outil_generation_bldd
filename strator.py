import streamlit as st
import pandas as pd
from datetime import date

st.title("📘 Génération écriture BLDD")

uploaded_file = st.file_uploader("📂 Importer le fichier BLDD (Excel)", type=["xlsx"])

if uploaded_file:
    df = pd.read_excel(uploaded_file)

    # Vérifications colonnes nécessaires
    colonnes_obligatoires = ["ISBN", "Vente", "Retour", "Net", "Facture"]
    for col in colonnes_obligatoires:
        if col not in df.columns:
            st.error(f"❌ Colonne manquante : {col}")
            st.stop()

    # Calcul des remises
    df["Remise_libraire"] = df["Net"] - df["Facture"]

    # Paramètres utilisateur
    journal = st.text_input("📒 Journal", value="VT")
    libelle_base = st.text_input("🧾 Libellé", value="Ventes mensuelles BLDD")
    date_ecriture = st.date_input("📅 Date d'écriture", value=date.today())
    com_diff = st.number_input("💼 Commission de diffusion (622800000)", value=0.0, step=100.0)
    com_dist = st.number_input("🚚 Commission de distribution (622800010)", value=0.0, step=100.0)
    reprise_prov = st.number_input("🔁 Reprise provision retours (montant TTC)", value=0.0, step=100.0)

    # Comptes utilisés
    comptes = {
        "ca_brut": "701100000",
        "retour": "709000000",
        "remise": "709100000",
        "tva_collectee": "445710060",
        "tva_deductible": "445660000",
        "com_diff": "622800000",
        "com_dist": "622800010",
        "provision": "681000000",
        "reprise_provision": "467100000",
        "client": "411100011"
    }

    lignes = []

    # CA brut, retour, remise libraire par ISBN
    for _, r in df.iterrows():
        isbn = r["ISBN"]
        vente = r["Vente"]
        retour = r["Retour"]
        remise = r["Remise_libraire"]
        facture = r["Facture"]

        # CA brut
        lignes.append([date_ecriture, journal, comptes["ca_brut"], f"{libelle_base} - CA brut", isbn, 0, vente])

        # Retours
        if retour != 0:
            lignes.append([date_ecriture, journal, comptes["retour"], f"{libelle_base} - Retours", isbn, abs(retour), 0])

        # Remises libraires
        if remise != 0:
            if remise > 0:
                lignes.append([date_ecriture, journal, comptes["remise"], f"{libelle_base} - Remises libraires", isbn, remise, 0])
            else:
                lignes.append([date_ecriture, journal, comptes["remise"], f"{libelle_base} - Remises libraires", isbn, 0, abs(remise)])

        # Provision 10% TTC
        provision = round(vente * 1.055 * 0.10, 2)
        if provision != 0:
            lignes.append([date_ecriture, journal, comptes["provision"], f"{libelle_base} - Provision retours (10% TTC)", isbn, provision, 0])

    # Commissions
    lignes.append([date_ecriture, journal, comptes["com_diff"], f"{libelle_base} - Commission diffusion", "GLOBAL", com_diff, 0])
    lignes.append([date_ecriture, journal, comptes["com_dist"], f"{libelle_base} - Commission distribution", "GLOBAL", com_dist, 0])

    # TVA déductible sur commissions (5.5%)
    tva_ded = round((com_diff + com_dist) * 0.055, 2)
    lignes.append([date_ecriture, journal, comptes["tva_deductible"], f"{libelle_base} - TVA déductible sur commissions", "GLOBAL", tva_ded, 0])

    # TVA collectée (5.5% sur CA net après remise et retour)
    ca_net = df["Facture"].sum()
    tva_col = round(ca_net * 0.055, 2)
    lignes.append([date_ecriture, journal, comptes["tva_collectee"], f"{libelle_base} - TVA collectée 5.5%", "GLOBAL", 0, tva_col])

    # Reprise provision (411 -> 467100)
    if reprise_prov != 0:
        lignes.append([date_ecriture, journal, comptes["reprise_provision"], f"{libelle_base} - Reprise provision retours", "GLOBAL", reprise_prov, 0])
        lignes.append([date_ecriture, journal, comptes["client"], f"{libelle_base} - Reprise provision retours", "GLOBAL", 0, reprise_prov])

    # Calcule du solde client
    total_debit = sum(l[5] for l in lignes)
    total_credit = sum(l[6] for l in lignes)
    solde_client = round(total_credit - total_debit, 2)

    # Ligne client globale pour équilibre
    if solde_client > 0:
        lignes.append([date_ecriture, journal, comptes["client"], f"{libelle_base} - Client global", "GLOBAL", solde_client, 0])
    else:
        lignes.append([date_ecriture, journal, comptes["client"], f"{libelle_base} - Client global", "GLOBAL", 0, abs(solde_client)])

    # Construction DataFrame final
    df_ecr = pd.DataFrame(lignes, columns=["Date", "Journal", "Compte", "Libellé", "ISBN", "Débit", "Crédit"])

    # Affichage
    st.subheader("🧾 Écritures comptables générées")
    st.dataframe(df_ecr, hide_index=True, use_container_width=True)

    st.write("**Total Débit :**", round(df_ecr["Débit"].sum(), 2))
    st.write("**Total Crédit :**", round(df_ecr["Crédit"].sum(), 2))
    st.write("**Équilibre :**", round(df_ecr["Débit"].sum() - df_ecr["Crédit"].sum(), 2))

    # Téléchargement
    st.download_button(
        "⬇️ Télécharger les écritures au format Excel",
        df_ecr.to_excel(index=False, engine="openpyxl"),
        file_name="ecritures_bldd.xlsx"
    )
