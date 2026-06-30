import { NextRequest, NextResponse } from 'next/server';

export async function POST(request: NextRequest) {
  try {
    const { text } = await request.json();

    if (!text || text.trim() === '') {
      return NextResponse.json(
        { error: 'Message text is required' },
        { status: 400 }
      );
    }

    // Call the Python Donald agent backend
    const apiUrl = process.env.DONALD_API_URL || 'http://localhost:8000';
    const response = await fetch(`${apiUrl}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ text }),
    });

    if (!response.ok) {
      console.error('Agent API error:', response.status, response.statusText);
      return NextResponse.json(
        { error: 'Failed to get response from agent' },
        { status: 500 }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error('Chat API error:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
