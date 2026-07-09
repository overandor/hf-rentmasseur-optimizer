#!/usr/bin/env node
/**
 * Transformers.js local LLM — runs entirely in Node.js, no API keys needed.
 *
 * Usage:
 *   echo "Your prompt here" | node rm_traffic/transformers_llm.js
 *   echo "Your prompt here" | node rm_traffic/transformers_llm.js --model Xenova/Phi-3.5-mini-instruct
 *   echo "Your prompt here" | node rm_traffic/transformers_llm.js --max-tokens 500
 *
 * Reads prompt from stdin, writes generated text to stdout.
 * First run downloads model (~2GB cached in ~/.cache/huggingface).
 */

const { pipeline, env } = require("@huggingface/transformers");

// Allow local models, disable remote loading errors on first run
env.allowLocalModels = false;

async function main() {
  const args = process.argv.slice(2);
  let modelName = "Xenova/Qwen2.5-0.5B-Instruct";
  let maxTokens = 800;

  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--model" && args[i + 1]) {
      modelName = args[i + 1];
      i++;
    } else if (args[i] === "--max-tokens" && args[i + 1]) {
      maxTokens = parseInt(args[i + 1], 10);
      i++;
    }
  }

  // Read prompt from stdin
  const chunks = [];
  for await (const chunk of process.stdin) {
    chunks.push(chunk);
  }
  const prompt = Buffer.concat(chunks).toString("utf-8").trim();

  if (!prompt) {
    console.error("ERROR: No prompt provided on stdin");
    process.exit(1);
  }

  try {
    process.stderr.write(`[transformers.js] Loading model: ${modelName}\n`);
    const t0 = Date.now();

    const pipe = await pipeline("text-generation", modelName, {
      device: "cpu",
    });

    process.stderr.write(`[transformers.js] Model loaded in ${((Date.now() - t0) / 1000).toFixed(1)}s\n`);

    const messages = [
      { role: "system", content: "You are a helpful assistant for a massage therapist optimization system. Be concise and direct." },
      { role: "user", content: prompt },
    ];

    const t1 = Date.now();
    const output = await pipe(messages, {
      max_new_tokens: maxTokens,
      temperature: 0.75,
      do_sample: true,
    });

    const elapsed = ((Date.now() - t1) / 1000).toFixed(1);
    process.stderr.write(`[transformers.js] Generated in ${elapsed}s\n`);

    // Extract text from output
    let text = "";
    if (Array.isArray(output) && output.length > 0) {
      const msg = output[0].generated_text;
      if (Array.isArray(msg)) {
        // Chat format: [{role, content}, ...]
        const last = msg[msg.length - 1];
        text = last?.content || "";
      } else if (typeof msg === "string") {
        text = msg;
      } else {
        text = JSON.stringify(msg);
      }
    } else if (typeof output === "string") {
      text = output;
    } else {
      text = JSON.stringify(output);
    }

    // Write only the generated text to stdout (clean for Python to consume)
    process.stdout.write(text.trim());
  } catch (err) {
    process.stderr.write(`[transformers.js] ERROR: ${err.message}\n`);
    process.exit(1);
  }
}

main();
