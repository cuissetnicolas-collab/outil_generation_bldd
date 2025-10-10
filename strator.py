import streamlit as st
import pandas as pd

st.title("💼 Génération des écritures de vente et provisions - Maison d’édition")

uploaded_file = st.file_uploader("📂 Importer le fichier des ventes (CSV ou Excel)", type=["csv", "xlsx"])

if uploaded_file:
    # Lecture du fichier
    try:
        if uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file, sep=";", decimal=",")
        else:
            df = pd.read_excel(uploaded_file)
    except Exception as e:
        st.error(f"Erreur lors de la lecture du fichier : {e}")
        st.stop()

    st.success("✅ Fichier importé avec succès !")

    # Vérification des colonnes minimales
    colonnes_requises = ["Titre", "CA_Brut_TTC", "Compte_analytique"]
    if not all(col in df.columns for col in colonnes_requises):
        st.error(f"⚠️ Le fichier doit contenir les colonnes suivantes : {colonnes_requises}")
        st.stop()

    # Taux et paramètres
    tva_ventes = 0.055
    taux_provision_retour = 0.10

    # Calcul des montants
    df["Provision_retour"] = df["CA_Brut_TTC"] * taux_provision_retour
    df["CA_net_provision"] = df["CA_Brut_TTC"] - df["Provision_retour"]

    # --- Écritures principales ---
    ecritures = []

    for _, row in df.iterrows():
        titre = row["Titre"]
        analytique = row["Compte_analytique"]

        # Ventes (HT et TVA)
        ca_ttc = row["CA_Brut_TTC"]
        ca_ht = ca_ttc / (1 + tva_ventes)
        tva = ca_ttc - ca_ht

        # Provision pour retour (681 analytique)
        provision = row["Provision_retour"]

        # Écriture 1 : Vente
        ecritures.append({
            "Compte": "411100000",
            "Libellé": f"Vente - {titre}",
            "Débit": ca_ttc,
            "Crédit": 0,
            "Analytique": ""
        })
        ecritures.append({
            "Compte": "706000000",
            "Libellé": f"Vente - {titre}",
            "Débit": 0,
            "Crédit": ca_ht,
            "Analytique": analytique
        })
        ecritures.append({
            "Compte": "445715000",
            "Libellé": f"TVA 5,5% - {titre}",
            "Débit": 0,
            "Crédit": tva,
            "Analytique": ""
        })

        # Écriture 2 : Provision pour retour
        ecritures.append({
            "Compte": "681000000",
            "Libellé": f"Provision retours {titre}",
            "Débit": provision,
            "Crédit": 0,
            "Analytique": analytique
        })
        ecritures.append({
            "Compte": "411100000",
            "Libellé": f"Provision retours {titre}",
            "Débit": 0,
            "Crédit": provision,
            "Analytique": ""
        })

    # --- Reprise des provisions ---
    st.subheader("🔁 Reprise des provisions")
    reprise = st.number_input("Montant total de la reprise à comptabiliser (€)", min_value=0.0, step=100.0)

    if reprise > 0:
        ecritures.append({
            "Compte": "467100000",
            "Libellé": "Reprise provision retour",
            "Débit": reprise,
            "Crédit": 0,
            "Analytique": ""
        })
        ecritures.append({
            "Compte": "411100000",
            "Libellé": "Reprise provision retour",
            "Débit": 0,
            "Crédit": reprise,
            "Analytique": ""
        })

    # --- Vérification équilibre ---
    df_ecr = pd.DataFrame(ecritures)
    total_debit = df_ecr["Débit"].sum()
    total_credit = df_ecr["Crédit"].sum()

    st.write("### 🧾 Aperçu des écritures générées")
    st.dataframe(df_ecr)

    st.write(f"**Total Débit :** {total_debit:,.2f} €")
    st.write(f"**Total Crédit :** {total_credit:,.2f} €")

    if abs(total_debit - total_credit) < 0.01:
        st.success("✅ Les écritures sont équilibrées.")
    else:
        st.error(f"⚠️ Les écritures ne sont pas équilibrées (écart de {total_debit - total_credit:,.2f} €).")

    # Export Excel
    output = df_ecr.to_excel(index=False)
    st.download_button("📤 Télécharger les écritures au format Excel", data=output, file_name="ecritures_provision.xlsx")

else:
    st.info("📎 Importez un fichier pour commencer.")
