import streamlit as st
import pandas as pd

st.title("📘 Génération des écritures comptables - Maison d’édition")

# --- Saisie utilisateur ---
journal = st.text_input("📒 Journal", value="VT")
date_ecriture = st.date_input("📅 Date de l’écriture")
famille_analytique = st.text_input("🏷️ Famille analytique", value="EDITION")
montant_reprise = st.number_input("💸 Montant de la reprise de provision (en €)", min_value=0.0, step=0.01)

# --- Fichier BLDD ---
fichier = st.file_uploader("📂 Importer le fichier BLDD (CSV ou Excel)", type=["csv", "xlsx"])

if fichier:
    try:
        if fichier.name.endswith(".csv"):
            df = pd.read_csv(fichier, sep=";", decimal=",")
        else:
            df = pd.read_excel(fichier)

        # Vérification colonnes
        colonnes_attendues = ["ISBN", "Facture", "Net"]
        for col in colonnes_attendues:
            if col not in df.columns:
                st.error(f"Colonne manquante dans le fichier : {col}")
                st.stop()

        # --- Calculs ---
        df["Remise_libraire"] = df["Facture"] - df["Net"]

        total_facture = df["Facture"].sum()
        total_net = df["Net"].sum()
        remise_total = df["Remise_libraire"].sum()

        # --- Provision 10% sur CA TTC ---
        provision = round(total_facture * 0.10, 2)

        # --- TVA déductible sur commissions (5,5% sur 622800+622801) ---
        tva_commission = round(remise_total * 0.055, 2)

        # --- Écritures comptables ---
        ecritures = []

        # 1. Vente (CA TTC)
        ecritures.append({
            "Journal": journal,
            "Date": date_ecriture,
            "Compte": "707100000",
            "Libellé": "Ventes ouvrages TTC",
            "Débit": 0,
            "Crédit": total_facture,
            "Catégorie analytique": "",
            "Famille analytique": famille_analytique
        })

        # 2. Commission diffuseur-distributeur
        ecritures.append({
            "Journal": journal,
            "Date": date_ecriture,
            "Compte": "622800000",
            "Libellé": "Commissions diffusion-distribution",
            "Débit": remise_total,
            "Crédit": 0,
            "Catégorie analytique": "",
            "Famille analytique": famille_analytique
        })

        # 3. TVA déductible sur commissions
        ecritures.append({
            "Journal": journal,
            "Date": date_ecriture,
            "Compte": "445660000",
            "Libellé": "TVA déductible 5,5% commissions",
            "Débit": tva_commission,
            "Crédit": 0,
            "Catégorie analytique": "",
            "Famille analytique": famille_analytique
        })

        # 4. Provision pour retour (681)
        ecritures.append({
            "Journal": journal,
            "Date": date_ecriture,
            "Compte": "681000000",
            "Libellé": "Dotation provision pour retours (10% CA TTC)",
            "Débit": provision,
            "Crédit": 0,
            "Catégorie analytique": "",
            "Famille analytique": famille_analytique
        })

        # 5. Reprise de provision (411 / 467100)
        if montant_reprise > 0:
            ecritures.append({
                "Journal": journal,
                "Date": date_ecriture,
                "Compte": "467100000",
                "Libellé": "Reprise de provision retours",
                "Débit": montant_reprise,
                "Crédit": 0,
                "Catégorie analytique": "",
                "Famille analytique": famille_analytique
            })
            ecritures.append({
                "Journal": journal,
                "Date": date_ecriture,
                "Compte": "411100000",
                "Libellé": "Reprise de provision retours",
                "Débit": 0,
                "Crédit": montant_reprise,
                "Catégorie analytique": "",
                "Famille analytique": famille_analytique
            })

        # --- Solde du 411 ---
        total_debit = sum(e["Débit"] for e in ecritures)
        total_credit = sum(e["Crédit"] for e in ecritures)
        difference = round(total_credit - total_debit, 2)

        if difference > 0:
            # Solde au débit
            ecritures.append({
                "Journal": journal,
                "Date": date_ecriture,
                "Compte": "411100000",
                "Libellé": "Solde client (équilibrage)",
                "Débit": difference,
                "Crédit": 0,
                "Catégorie analytique": "",
                "Famille analytique": famille_analytique
            })
        elif difference < 0:
            # Solde au crédit
            ecritures.append({
                "Journal": journal,
                "Date": date_ecriture,
                "Compte": "411100000",
                "Libellé": "Solde client (équilibrage)",
                "Débit": 0,
                "Crédit": abs(difference),
                "Catégorie analytique": "",
                "Famille analytique": famille_analytique
            })

        df_ecritures = pd.DataFrame(ecritures)

        # ✅ Vérification analytique pour éviter le blocage
        df_ecritures["Catégorie analytique"] = df_ecritures["Catégorie analytique"].replace("", "GLOBAL")
        df_ecritures["Famille analytique"] = df_ecritures["Famille analytique"].replace("", famille_analytique)

        st.dataframe(df_ecritures)

        # Export
        csv = df_ecritures.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")
        st.download_button("📥 Télécharger les écritures comptables", csv, "ecritures_comptables.csv", "text/csv")

    except Exception as e:
        st.error(f"Erreur lors du traitement du fichier : {e}")
