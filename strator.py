import streamlit as st
import pandas as pd

st.header("📘 Génération des écritures de ventes - Maison d’édition")

# --- Paramètres généraux ---
journal = st.text_input("📒 Journal", value="VT")
taux_tva = 0.055  # TVA à 5,5 %

uploaded_file = st.file_uploader("📂 Importer le fichier BLDD", type=["xlsx", "xls"])

if uploaded_file:
    df = pd.read_excel(uploaded_file)
    df.columns = df.columns.str.strip()

    # --- Calculs de base ---
    df["Remise_libraire"] = df["Net"] - df["Facture"]
    df["CA_Brut_TTC"] = df["Vente"]
    df["CA_Brut_HT"] = df["CA_Brut_TTC"] / (1 + taux_tva)
    df["Retour_TTC"] = df["Retour"].abs()  # positiver les retours
    df["Retour_HT"] = df["Retour_TTC"] / (1 + taux_tva)
    df["Remise_libraire_HT"] = df["Remise_libraire"] / (1 + taux_tva)

    # --- Commission diffuseur/distributeur ---
    df["Commission_diffusion_HT"] = df["Commission_diffusion"]
    df["Commission_distribution_HT"] = df["Commission_distribution"]
    df["TVA_deductible"] = (df["Commission_diffusion_HT"] + df["Commission_distribution_HT"]) * taux_tva

    # --- Provision à 10 % du TTC (avant retour/remise) ---
    df["Provision_TTC"] = df["CA_Brut_TTC"] * 0.10
    df["Provision_HT"] = df["Provision_TTC"] / (1 + taux_tva)

    ecritures = []

    # --- Génération des écritures par ISBN ---
    for _, row in df.iterrows():
        isbn = row["ISBN"]

        # 7011 - CA Brut
        ecritures.append({
            "Journal": journal,
            "Compte": "701100000",
            "Libellé": f"CA Brut {isbn}",
            "Débit": 0.0,
            "Crédit": row["CA_Brut_HT"],
            "Analytique": isbn,
            "ISBN": isbn
        })

        # 7090 - Retours
        ecritures.append({
            "Journal": journal,
            "Compte": "709000000",
            "Libellé": f"Retours {isbn}",
            "Débit": row["Retour_HT"],
            "Crédit": 0.0,
            "Analytique": isbn,
            "ISBN": isbn
        })

        # 7091 - Remises libraires
        montant_remise = abs(row["Remise_libraire_HT"])
        if row["Remise_libraire_HT"] < 0:
            ecritures.append({
                "Journal": journal,
                "Compte": "709100000",
                "Libellé": f"Remise libraire {isbn}",
                "Débit": 0.0,
                "Crédit": montant_remise,
                "Analytique": isbn,
                "ISBN": isbn
            })
        else:
            ecritures.append({
                "Journal": journal,
                "Compte": "709100000",
                "Libellé": f"Remise libraire {isbn}",
                "Débit": montant_remise,
                "Crédit": 0.0,
                "Analytique": isbn,
                "ISBN": isbn
            })

        # 6228 - Commissions
        total_commission = row["Commission_diffusion_HT"] + row["Commission_distribution_HT"]
        if total_commission >= 0:
            ecritures.append({
                "Journal": journal,
                "Compte": "622800000",
                "Libellé": f"Commissions diffusion/distribution {isbn}",
                "Débit": total_commission,
                "Crédit": 0.0,
                "Analytique": isbn,
                "ISBN": isbn
            })
        else:
            ecritures.append({
                "Journal": journal,
                "Compte": "622800000",
                "Libellé": f"Commissions diffusion/distribution {isbn}",
                "Débit": 0.0,
                "Crédit": abs(total_commission),
                "Analytique": isbn,
                "ISBN": isbn
            })

        # 681 - Provision (analytique)
        ecritures.append({
            "Journal": journal,
            "Compte": "681000000",
            "Libellé": f"Provision sur ventes {isbn}",
            "Débit": row["Provision_HT"],
            "Crédit": 0.0,
            "Analytique": isbn,
            "ISBN": isbn
        })

    # --- Écritures globales TVA & client ---
    total_tva_collectee = ((df["CA_Brut_HT"] - df["Retour_HT"] - df["Remise_libraire_HT"]) * taux_tva).sum()
    total_tva_deductible = df["TVA_deductible"].sum()

    total_ca_net_ht = (df["CA_Brut_HT"] - df["Retour_HT"] - df["Remise_libraire_HT"]).sum()
    total_commissions = (df["Commission_diffusion_HT"] + df["Commission_distribution_HT"]).sum()
    total_provisions = df["Provision_HT"].sum()

    total_client = total_ca_net_ht + total_tva_collectee - total_commissions - total_tva_deductible - total_provisions

    # TVA collectée
    ecritures.append({
        "Journal": journal,
        "Compte": "445710000",
        "Libellé": "TVA collectée",
        "Débit": 0.0,
        "Crédit": total_tva_collectee,
        "Analytique": "",
        "ISBN": ""
    })

    # TVA déductible sur commissions
    ecritures.append({
        "Journal": journal,
        "Compte": "445660000",
        "Libellé": "TVA déductible sur commissions",
        "Débit": total_tva_deductible,
        "Crédit": 0.0,
        "Analytique": "",
        "ISBN": ""
    })

    # Compte client (solde)
    ecritures.append({
        "Journal": journal,
        "Compte": "411100011",
        "Libellé": "Client BLDD",
        "Débit": total_client,
        "Crédit": 0.0,
        "Analytique": "",
        "ISBN": ""
    })

    # --- Reprise de provision ---
    montant_reprise = st.number_input("💫 Montant de la reprise de provision (TTC)", min_value=0.0, step=100.0)
    if montant_reprise > 0:
        ecritures.append({
            "Journal": journal,
            "Compte": "467100000",
            "Libellé": "Reprise de provision sur ventes",
            "Débit": montant_reprise,
            "Crédit": 0.0,
            "Analytique": "",
            "ISBN": ""
        })
        ecritures.append({
            "Journal": journal,
            "Compte": "411100011",
            "Libellé": "Reprise de provision sur ventes",
            "Débit": 0.0,
            "Crédit": montant_reprise,
            "Analytique": "",
            "ISBN": ""
        })

    # --- Affichage ---
    ecritures_df = pd.DataFrame(ecritures)
    st.dataframe(ecritures_df)

    # --- Export Excel ---
    output = pd.ExcelWriter("ecritures_bldd.xlsx", engine="xlsxwriter")
    ecritures_df.to_excel(output, index=False, sheet_name="Écritures")
    output.close()
    st.success("✅ Fichier 'ecritures_bldd.xlsx' généré avec succès.")
