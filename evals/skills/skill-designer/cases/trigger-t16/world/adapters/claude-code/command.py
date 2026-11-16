def command(prompt_file, folder, model):
    return ["claude", "-p", "--model", model, "--add-dir", folder, "<", prompt_file]
