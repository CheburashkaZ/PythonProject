import tkinter as tk
from tkinter import messagebox, Listbox, END
import sqlite3
from contextlib import closing


# --- Логика экспертной системы ---

def perform_inference(knowledge_base, goal=None):
    """
    Прямой вывод: ищем диагноз по симптомам.
    Обратный вывод (если задан goal): ищем симптомы по названию болезни.
    """
    results = []
    user_symptoms = set(knowledge_base["facts"]["symptoms"])

    for rule in knowledge_base["rules"]:
        rule_symptoms = set(rule["if"]["symptoms"])

        if goal:
            # Если ищем по названию болезни (обратный поиск)
            if rule["then"]["diagnosis"].lower() == goal.lower():
                results.append(rule)
        else:
            # Если ищем диагноз по симптомам (прямой поиск)
            # Если все симптомы правила присутствуют в списке пользователя
            if rule_symptoms.issubset(user_symptoms) and rule_symptoms:
                results.append(rule["then"])

    return results


def explain_result(possible_diagnoses, knowledge_base):
    """Формирует объяснение, почему был выбран этот диагноз."""
    explanation = ""
    user_symptoms = ", ".join(knowledge_base["facts"]["symptoms"])
    for diag in possible_diagnoses:
        explanation += f"Диагноз '{diag['diagnosis']}' поставлен, так как вы указали симптомы, характерные для него.\n"
    return explanation


# --- Работа с базой данных ---

def init_db():
    with closing(sqlite3.connect('expert_system.db')) as conn:
        with conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS rules 
                            (id INTEGER PRIMARY KEY AUTOINCREMENT, diagnosis TEXT NOT NULL)''')
            conn.execute('''CREATE TABLE IF NOT EXISTS rule_symptoms 
                            (rule_id INTEGER, symptom TEXT NOT NULL, FOREIGN KEY (rule_id) REFERENCES rules(id) ON DELETE CASCADE)''')
            conn.execute('''CREATE TABLE IF NOT EXISTS rule_recommendations 
                            (rule_id INTEGER, recommendation TEXT NOT NULL, FOREIGN KEY (rule_id) REFERENCES rules(id) ON DELETE CASCADE)''')
            conn.execute('''CREATE TABLE IF NOT EXISTS current_symptoms 
                            (symptom TEXT PRIMARY KEY)''')


def load_initial_data():
    with closing(sqlite3.connect('expert_system.db')) as conn:
        with conn:
            cursor = conn.execute("SELECT COUNT(*) FROM rules")
            if cursor.fetchone()[0] == 0:
                initial_rules = [
                    {
                        "diagnosis": "солнечный удар",
                        "symptoms": ["головокружение", "высокая температура", "тошнота"],
                        "recommendations": [
                            "Принять жаропонижающее",
                            "Перейти в прохладное место",
                            "Лечь и поднять голову",
                            "При рвоте лечь на бок"
                        ]
                    },
                    {
                        "diagnosis": "простуда",
                        "symptoms": ["кашель", "насморк"],
                        "recommendations": ["Пить много теплой жидкости", "Соблюдать покой"]
                    }
                ]
                for rule in initial_rules:
                    conn.execute("INSERT INTO rules (diagnosis) VALUES (?)", (rule["diagnosis"],))
                    rule_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                    for s in rule["symptoms"]:
                        conn.execute("INSERT INTO rule_symptoms (rule_id, symptom) VALUES (?, ?)", (rule_id, s))
                    for r in rule["recommendations"]:
                        conn.execute("INSERT INTO rule_recommendations (rule_id, recommendation) VALUES (?, ?)",
                                     (rule_id, r))


def load_knowledge_base():
    kb = {"rules": [], "facts": {"symptoms": []}}
    with closing(sqlite3.connect('expert_system.db')) as conn:
        cursor = conn.execute("SELECT id, diagnosis FROM rules")
        for r_id, diag in cursor.fetchall():
            rule = {"if": {"symptoms": []}, "then": {"diagnosis": diag, "recommendations": []}}
            s_cur = conn.execute("SELECT symptom FROM rule_symptoms WHERE rule_id = ?", (r_id,))
            rule["if"]["symptoms"] = [s[0] for s in s_cur.fetchall()]
            rec_cur = conn.execute("SELECT recommendation FROM rule_recommendations WHERE rule_id = ?", (r_id,))
            rule["then"]["recommendations"] = [r[0] for r in rec_cur.fetchall()]
            kb["rules"].append(rule)

        f_cur = conn.execute("SELECT symptom FROM current_symptoms")
        kb["facts"]["symptoms"] = [f[0] for f in f_cur.fetchall()]
    return kb


def save_knowledge_base(kb):
    with closing(sqlite3.connect('expert_system.db')) as conn:
        with conn:
            conn.execute("DELETE FROM current_symptoms")
            for symptom in kb["facts"]["symptoms"]:
                conn.execute("INSERT INTO current_symptoms (symptom) VALUES (?)", (symptom,))


# --- Интерфейс ---

class ExpertSystemApp:
    def __init__(self, root):
        init_db()
        load_initial_data()
        self.root = root
        self.root.title("Экспертная система")
        self.knowledge_base = load_knowledge_base()

        tk.Label(root, text="Введите симптом:").grid(row=0, column=0)
        self.fact_entry = tk.Entry(root, width=30)
        self.fact_entry.grid(row=0, column=1)

        self.add_button = tk.Button(root, text="Добавить", command=self.add_fact)
        self.add_button.grid(row=0, column=2)

        self.fact_listbox = Listbox(root, width=50, height=8)
        self.fact_listbox.grid(row=1, column=0, columnspan=3, pady=10)

        tk.Button(root, text="Удалить симптом", command=self.delete_fact).grid(row=2, column=0)
        tk.Button(root, text="Диагностика", command=self.get_result, bg="lightgreen").grid(row=2, column=1)

        tk.Label(root, text="Поиск по болезни:").grid(row=3, column=0, pady=10)
        self.disease_entry = tk.Entry(root, width=30)
        self.disease_entry.grid(row=3, column=1)
        tk.Button(root, text="Найти", command=self.get_symptoms_by_disease).grid(row=3, column=2)

        for s in self.knowledge_base["facts"]["symptoms"]:
            self.fact_listbox.insert(END, s)

    def add_fact(self):
        fact = self.fact_entry.get().strip().lower()
        if fact and fact not in self.knowledge_base["facts"]["symptoms"]:
            self.knowledge_base["facts"]["symptoms"].append(fact)
            self.fact_listbox.insert(END, fact)
            save_knowledge_base(self.knowledge_base)
            self.fact_entry.delete(0, END)

    def delete_fact(self):
        selected = self.fact_listbox.curselection()
        if selected:
            fact = self.fact_listbox.get(selected)
            self.knowledge_base["facts"]["symptoms"].remove(fact)
            self.fact_listbox.delete(selected)
            save_knowledge_base(self.knowledge_base)

    def get_result(self):
        results = perform_inference(self.knowledge_base)
        if results:
            msg = ""
            for r in results:
                msg += f"Диагноз: {r['diagnosis']}\nРекомендации:\n- " + "\n- ".join(r['recommendations']) + "\n\n"
            msg += "Объяснение:\n" + explain_result(results, self.knowledge_base)
            messagebox.showinfo("Результат", msg)
        else:
            messagebox.showinfo("Результат", "Диагноз не найден. Попробуйте добавить больше симптомов.")

    def get_symptoms_by_disease(self):
        disease = self.disease_entry.get().strip()
        results = perform_inference(self.knowledge_base, goal=disease)
        if results:
            r = results[0]
            msg = f"Болезнь: {r['then']['diagnosis']}\nНужные симптомы: {', '.join(r['if']['symptoms'])}\n\nРекомендации:\n- " + "\n- ".join(
                r['then']['recommendations'])
            messagebox.showinfo("Инфо", msg)
        else:
            messagebox.showerror("Ошибка", "Болезнь не найдена.")


if __name__ == "__main__":
    root = tk.Tk()
    app = ExpertSystemApp(root)
    root.mainloop()