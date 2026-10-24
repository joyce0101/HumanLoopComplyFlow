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
from sklearn.metrics import accuracy_score, roc_auc_score, brier_score_loss
try:
    from .schemas import Prediction
except ImportError:
    from schemas import Prediction

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
    "case_id":"LOAN-001","checking_status":"A11","duration":30,
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

def sample_cases(n: int) -> list[dict]:
    """从训练时固定划分的测试集抽取 n 条申请（团队 PLAN.md 3.2 接口）。

    为避免测试集泄露到模型拟合，使用与 train() 完全相同的 random_state=42
    和 stratify=y 规则重建测试集索引。返回的字典不含目标标签。
    每条案例默认添加 identity_verified=True，便于风险闸门识别业务元信息。
    """
    if type(n) is not int or n < 0:
        raise ValueError("n 必须是非负整数")
    X, y = load_data(DATA_FILE)
    _, x_test, _, _ = train_test_split(
        X, y, test_size=.25, random_state=42, stratify=y
    )
    if n > len(x_test):
        raise ValueError(f"最多可以抽取 {len(x_test)} 条测试案例")
    # 固定打乱顺序，反复 Demo 时结果可重现。
    selected = x_test.sample(n=n, random_state=42)
    cases = []
    for _, row in selected.iterrows():
        record = {key: (value.item() if isinstance(value, np.generic) else value)
                  for key, value in row.to_dict().items()}
        record["identity_verified"] = True  # 演示业务字段，并非 German Credit 原始特征
        cases.append(record)
    return cases


def predict(features: dict, case_id: str, model_path=MODEL_FILE) -> Prediction:
    """根据申请特征和唯一案例编号生成 Prediction（团队 PLAN.md 3.2 接口）。

    features: 20 项 German Credit 输入特征，可附加 identity_verified 等业务字段。
    case_id: 由调用方提供，必须是非空字符串。
    不重新训练模型，只加载经过可信训练保存的 joblib 文件。
    top_factors 返回绝对值最大的 10 项有符号 log-odds 贡献，不是 SHAP。
    """
    if not isinstance(case_id, str) or not case_id.strip():
        raise ValueError("case_id 必须是非空字符串")
    if not isinstance(features, dict):
        raise TypeError("features 必须是字典")
    application = dict(features)
    # 允许用户将 case_id 放入 features，但不允许出现两个不一致的编号。
    if "case_id" in application and application["case_id"] != case_id:
        raise ValueError("features.case_id 与 case_id 参数不一致")
    application.pop("case_id", None)
    bundle=load_model(str(Path(model_path)))
    pipeline=bundle["pipeline"]
    x=_prepare(application)
    p=float(pipeline.predict_proba(x)[0,1])
    feature_transformer=pipeline.named_steps["features"]
    z=feature_transformer.transform(x)
    z=z.toarray()[0] if hasattr(z,"toarray") else z[0]
    contributions=z*pipeline.named_steps["classifier"].coef_[0]
    feature_names=feature_transformer.get_feature_names_out()
    top=np.argsort(np.abs(contributions))[-10:][::-1]
    factors=[(str(feature_names[i]), round(float(contributions[i]), 4)) for i in top]
    # Use only known features for ML input, but retain provided extra demo policy fields.
    return Prediction(
        case_id=case_id,
        features=dict(application),
        decision="reject" if p >= 0.5 else "approve",
        confidence=round(max(p, 1-p), 4),
        top_factors=factors,
        is_gold=False,
        gold_correct_decision=None,
    )

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--train",action="store_true")
    parser.add_argument("--data",type=Path,default=DATA_FILE)
    parser.add_argument("--model",type=Path,default=MODEL_FILE)
    args=parser.parse_args()
    if args.train:
        result=train(args.data,args.model)
    else:
        result=predict(EXAMPLE_APPLICATION,"LOAN-001",args.model)
    from dataclasses import asdict, is_dataclass
    print(json.dumps(asdict(result) if is_dataclass(result) else result,
                     indent=2,ensure_ascii=False))
