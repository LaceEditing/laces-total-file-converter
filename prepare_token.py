import os

def main():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("ERROR: GITHUB_TOKEN is not set in the environment.")
        print("Cannot embed token; build will fail.")
        return

    with open("embed_token.py", "r", encoding="utf-8") as f:
        lines = f.readlines()

    new_lines = []
    for line in lines:
        if line.strip().startswith("GITHUB_TOKEN = "):
            new_lines.append(f'GITHUB_TOKEN = "{token}"\n')
        else:
            new_lines.append(line)

    with open("embed_token.py", "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    print("Token embedded successfully.")

if __name__ == "__main__":
    main()
