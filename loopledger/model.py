"""LoopLedger German Credit model. Demonstration only, not for real lending."""
from pathlib import Path
from functools import lru_cache
import argparse
import json
import numpy as np
import pandas as pd
import joblib
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, roc_auc_score, brier_score_loss, classification_report

BASE_DIR = Path(__file__).resolve().parent
# Dataset is located one level above loopledger/
PROJECT_ROOT = BASE_DIR.parent
DATA_FILE = (
    PROJECT_ROOT
    / "dataset"
    / "statlog+german+credit+data"
    / "german.data"
)
MODEL_FILE = BASE_DIR / "credit_model.joblib"
MODEL_VERSION = "german-credit-logreg-v2"

COLS = ["checking_status","duration","credit_history","purpose","credit_amount",
        "savings_status","employment","installment_commitment","personal_status",
        "other_parties","residence_since","property_magnitude","age",
        "other_payment_plans","housing","existing_credits","job",
        "num_dependents","own_telephone","foreign_worker","target"]
FEATURES = COLS[:-1]
NUMERIC = ["duration","credit_amount","installment_commitment",
           "residence_since","age","existing_credits","num_dependents"]
CATEGORICAL = [x for x in FEATURES if x not in NUMERIC]
CATEGORY_CODES = {
    "checking_status":["A11","A12","A13","A14"],
    "credit_history":["A30","A31","A32","A33","A34"],
    "purpose":["A40","A41","A42","A43","A44","A45","A46","A48","A49","A410"],
    "savings_status":["A61","A62","A63","A64","A65"],
    "employment":["A71","A72","A73","A74","A75"],
    "personal_status":["A91","A92","A93","A94","A95"],
    "other_parties":["A101","A102","A103"],
    "property_magnitude":["A121","A122","A123","A124"],
    "other_payment_plans":["A141","A142","A143"],
    "housing":["A151","A152","A153"],
    "job":["A171","A172","A173","A174"],
    "own_telephone":["A191","A192"],
    "foreign_worker":["A201","A202"]
}
EXAMPLE_APPLICATION = {
    "decision_id":"LOAN-001","checking_status":"A11","duration":30,
    "credit_history":"A32","purpose":"A40","credit_amount":16000,
    "savings_status":"A61","employment":"A73","installment_commitment":3,
    "personal_status":"A93","other_parties":"A101","residence_since":2,
    "property_magnitude":"A123","age":35,"other_payment_plans":"A143",
    "housing":"A152","existing_credits":1,"job":"A173",
    "num_dependents":1,"own_telephone":"A191","foreign_worker":"A201",
    "identity_verified":True
}

def load_data(path=DATA_FILE):
    path=Path(path)
    if not path.is_file():
        raise FileNotFoundError(
            f"Cannot find {path}. Copy german.data to the dataset folder shown in README.")
    df=pd.read_csv(path,sep=r"\s+",header=None,names=COLS)
    if df.shape[1]!=21 or df.empty:
        raise ValueError("Expected a nonempty german.data with 21 columns")
    labels=pd.to_numeric(df["target"],errors="coerce")
    if labels.isna().any() or not labels.isin([1,2]).all():
        raise ValueError("Expected German Credit labels 1 (good) and 2 (bad)")
    if df[FEATURES].isna().any().any():
        raise ValueError("Dataset has missing features")
    for field in CATEGORICAL:
        if not df[field].astype(str).isin(CATEGORY_CODES[field]).all():
            raise ValueError(f"Invalid category codes for {field}")
    for field in NUMERIC:
        df[field]=pd.to_numeric(df[field],errors="raise")
    return df[FEATURES], (labels==2).astype(int)

def train(data_path=DATA_FILE,model_path=MODEL_FILE):
    X,y=load_data(data_path)
    x_train,x_test,y_train,y_test=train_test_split(
        X,y,test_size=.25,random_state=42,stratify=y)
    transformer=ColumnTransformer([
        ("num",StandardScaler(),NUMERIC),
        ("cat",OneHotEncoder(handle_unknown="ignore",categories=[
            CATEGORY_CODES[f] for f in CATEGORICAL]),CATEGORICAL)
    ])
    pipeline=Pipeline([
        ("features",transformer),
        ("classifier",LogisticRegression(max_iter=1500,random_state=42))
    ])
    pipeline.fit(x_train,y_train)
    p=pipeline.predict_proba(x_test)[:,1]
    metrics={
        "dataset":"UCI Statlog German Credit (local file)",
        "train_rows":int(len(x_train)),
        "test_rows":int(len(x_test)),
        "accuracy":round(float(accuracy_score(y_test,p>=.5)),4),
        "roc_auc":round(float(roc_auc_score(y_test,p)),4),
        "brier_score":round(float(brier_score_loss(y_test,p)),4)
    }
    model_path=Path(model_path)
    model_path.parent.mkdir(parents=True,exist_ok=True)
    joblib.dump({"pipeline":pipeline,"version":MODEL_VERSION,"metrics":metrics},
                model_path)
    load_model.cache_clear()
    return metrics

@lru_cache(maxsize=4)
def load_model(path=str(MODEL_FILE)):
    path=Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"No trained model at {path}. Run: python model.py --train")
    # Only load joblib artifacts created by your own trusted training code.
    return joblib.load(path)

def _prepare(application):
    missing=[f for f in FEATURES if application.get(f) is None]
    if missing:
        raise ValueError(f"Missing features: {missing}")
    row={}
    for f in NUMERIC:
        try: val=float(application[f])
        except (TypeError,ValueError) as ex: raise ValueError(f"Invalid numeric {f}") from ex
        if not np.isfinite(val):
            raise ValueError(f"Nonfinite numeric {f}")
        row[f]=val
    for f in CATEGORICAL:
        val=str(application[f])
        if val not in CATEGORY_CODES[f]:
            raise ValueError(f"Invalid {f}: {val}")
        row[f]=val
    return pd.DataFrame([row],columns=FEATURES)

def predict(application:dict, model_path=MODEL_FILE)->dict:
    bundle=load_model(str(Path(model_path)))
    pipeline=bundle["pipeline"]
    x=_prepare(application)
    p=float(pipeline.predict_proba(x)[0,1])
    feature_transformer=pipeline.named_steps["features"]
    z=feature_transformer.transform(x)
    z=z.toarray()[0] if hasattr(z,"toarray") else z[0]
    contributions=z*pipeline.named_steps["classifier"].coef_[0]
    feature_names=feature_transformer.get_feature_names_out()
    top=np.argsort(np.abs(contributions))[-5:][::-1]
    explanations=[{"feature":str(feature_names[i]),
                   "contribution_to_default_log_odds":round(float(contributions[i]),4)}
                  for i in top]
    return {
        "decision_id":str(application.get("decision_id","UNASSIGNED")),
        "model_version":bundle["version"],
        "prediction":"reject" if p>=.5 else "approve",
        "probability_default":round(p,4),
        "confidence":round(max(p,1-p),4),
        "explanation":explanations,
        "dataset":bundle["metrics"]["dataset"],
        "disclaimer":"Educational demonstration only, not for real credit decisions."
    }

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--train",action="store_true")
    parser.add_argument("--data",type=Path,default=DATA_FILE)
    parser.add_argument("--model",type=Path,default=MODEL_FILE)
    args=parser.parse_args()
    if args.train:
        result=train(args.data,args.model)
    else:
        result=predict(EXAMPLE_APPLICATION,args.model)
    print(json.dumps(result,indent=2,ensure_ascii=False))
