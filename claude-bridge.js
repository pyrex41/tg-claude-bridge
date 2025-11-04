#!/usr/bin/env node
/**
 * Claude Code SDK Bridge
 * Provides a simple interface for Python to call Claude using the SDK
 */

import { claude } from '@instantlyeasy/claude-code-sdk-ts';

async function main() {
  const args = process.argv.slice(2);

  if (args.length === 0) {
    console.error('Usage: claude-bridge.js <prompt> [--model=MODEL] [--continuation-id=ID] [--tools=TOOL1,TOOL2]');
    process.exit(1);
  }

  // Parse arguments
  let prompt = '';
  let model = 'claude-sonnet-4-5-20250929';
  let continuationId = null;
  let tools = null;

  for (const arg of args) {
    if (arg.startsWith('--model=')) {
      model = arg.split('=')[1];
    } else if (arg.startsWith('--continuation-id=')) {
      continuationId = arg.split('=')[1];
    } else if (arg.startsWith('--tools=')) {
      tools = arg.split('=')[1].split(',');
    } else if (!arg.startsWith('--')) {
      prompt += (prompt ? ' ' : '') + arg;
    }
  }

  try {
    // Build Claude query
    let query = claude().withModel(model);

    // Add tools if specified
    if (tools && tools.length > 0) {
      query = query.allowTools(...tools);
    }

    // Execute query
    const result = await query.query(prompt).asResult();

    // Extract text response
    let responseText = '';
    for (const message of result.messages) {
      if (message.type === 'assistant') {
        for (const block of message.content) {
          if (block.type === 'text') {
            responseText += block.text;
          }
        }
      }
    }

    // Output JSON response
    const output = {
      response: responseText,
      continuation_id: result.session_id || null,
      usage: {
        input_tokens: result.usage?.input_tokens || 0,
        output_tokens: result.usage?.output_tokens || 0,
        total_cost: result.totalCost || 0
      }
    };

    console.log(JSON.stringify(output));
    process.exit(0);

  } catch (error) {
    console.error(JSON.stringify({
      error: error.message,
      type: error.name
    }));
    process.exit(1);
  }
}

main();
