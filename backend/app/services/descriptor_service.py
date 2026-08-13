"""分子描述符计算（纯函数）。"""

from __future__ import annotations

from rdkit import Chem
from rdkit.Chem import Descriptors, Lipinski, rdMolDescriptors


def lipinski_violations(mol: Chem.Mol) -> int:
    """Lipinski 五规则违反数（MW>500 / LogP>5 / HBD>5 / HBA>10 计次）。"""
    violations = 0
    if Descriptors.MolWt(mol) > 500:
        violations += 1
    if Descriptors.MolLogP(mol) > 5:
        violations += 1
    if Lipinski.NumHDonors(mol) > 5:
        violations += 1
    if Lipinski.NumHAcceptors(mol) > 10:
        violations += 1
    return violations


def compute_descriptors(mol: Chem.Mol) -> dict:
    """计算全部展示/比较用描述符。mol 需已 sanitize。"""
    return {
        "molecular_formula": rdMolDescriptors.CalcMolFormula(mol),
        "formal_charge": Chem.GetFormalCharge(mol),
        "heavy_atom_count": mol.GetNumHeavyAtoms(),
        "rotatable_bonds": Lipinski.NumRotatableBonds(mol),
        "MolWt": round(Descriptors.MolWt(mol), 3),  # g/mol
        "LogP": round(Descriptors.MolLogP(mol), 3),
        "TPSA": round(Descriptors.TPSA(mol), 3),  # Å²
        "HBD": Lipinski.NumHDonors(mol),
        "HBA": Lipinski.NumHAcceptors(mol),
        "fraction_csp3": round(Lipinski.FractionCSP3(mol), 3),
        "ring_count": Lipinski.RingCount(mol),
        "lipinski_violations": lipinski_violations(mol),
        "canonical_smiles": Chem.MolToSmiles(mol),
        "isomeric_smiles": Chem.MolToSmiles(mol, isomericSmiles=True),
    }
