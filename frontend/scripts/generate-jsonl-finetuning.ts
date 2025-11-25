/**
 * OpenAI Fine-tuning을 위한 JSONL 데이터 생성 스크립트 (TypeScript/Node.js 버전)
 * 
 * 사용자가 직접 수정한 번역 데이터(userEdited=true)만 추출하여
 * OpenAI Chat Fine-tuning 형식으로 변환합니다.
 * 
 * 필요한 DB 테이블 구조:
 * - originalText: 영문 원문
 * - editedText: 사람이 수정한 최종 번역문
 * - userEdited: boolean (true인 레코드만 사용)
 * 
 * 실행 방법:
 * npm install -g tsx  (또는 ts-node)
 * tsx frontend/scripts/generate-jsonl-finetuning.ts
 */

import * as fs from 'fs';
import * as path from 'path';

// 시스템 프롬프트 - Cadwell Korea 의료기기 브로셔 전문 번역가
const SYSTEM_PROMPT = 'Cadwell Korea 의료기기 브로셔 전문 번역가';

// JSONL 파일 저장 경로
const OUTPUT_FILE = 'training_data.jsonl';

// 번역 데이터 타입
interface Translation {
  originalText: string;
  editedText: string;
}

// OpenAI Fine-tuning 메시지 형식
interface OpenAIMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

interface OpenAITrainingExample {
  messages: OpenAIMessage[];
}


/**
 * SQLite DB에서 사용자가 수정한 번역 데이터를 가져옵니다.
 * npm install better-sqlite3 필요
 */
async function getEditedTranslationsFromSQLite(dbPath: string): Promise<Translation[]> {
  try {
    // better-sqlite3 동적 import
    const Database = (await import('better-sqlite3')).default;
    const db = new Database(dbPath);
    
    const query = `
      SELECT originalText, editedText 
      FROM translations 
      WHERE userEdited = 1 
      AND originalText IS NOT NULL 
      AND editedText IS NOT NULL
      AND originalText != ''
      AND editedText != ''
      ORDER BY id DESC
    `;
    
    const rows = db.prepare(query).all() as Translation[];
    db.close();
    
    console.log(`✅ SQLite DB에서 ${rows.length}개의 사용자 수정 번역 데이터를 가져왔습니다.`);
    return rows;
    
  } catch (error) {
    console.error('❌ SQLite 연결 오류:', error);
    console.log('   npm install better-sqlite3 를 먼저 실행하세요.');
    return [];
  }
}


/**
 * PostgreSQL DB에서 사용자가 수정한 번역 데이터를 가져옵니다.
 * npm install pg 필요
 */
async function getEditedTranslationsFromPostgreSQL(
  host: string = 'localhost',
  port: number = 5432,
  database: string = 'translation_db',
  user: string = 'postgres',
  password: string = ''
): Promise<Translation[]> {
  try {
    // pg 동적 import
    const { Client } = await import('pg');
    
    const client = new Client({
      host,
      port,
      database,
      user,
      password,
    });
    
    await client.connect();
    
    const query = `
      SELECT original_text as "originalText", edited_text as "editedText"
      FROM translations 
      WHERE user_edited = true 
      AND original_text IS NOT NULL 
      AND edited_text IS NOT NULL
      AND original_text != ''
      AND edited_text != ''
      ORDER BY id DESC
    `;
    
    const result = await client.query(query);
    await client.end();
    
    console.log(`✅ PostgreSQL DB에서 ${result.rows.length}개의 사용자 수정 번역 데이터를 가져왔습니다.`);
    return result.rows;
    
  } catch (error) {
    console.error('❌ PostgreSQL 연결 오류:', error);
    console.log('   npm install pg 를 먼저 실행하세요.');
    return [];
  }
}


/**
 * MongoDB에서 사용자가 수정한 번역 데이터를 가져옵니다.
 * npm install mongodb 필요
 */
async function getEditedTranslationsFromMongoDB(
  uri: string = 'mongodb://localhost:27017',
  dbName: string = 'translation_db',
  collectionName: string = 'translations'
): Promise<Translation[]> {
  try {
    // mongodb 동적 import
    const { MongoClient } = await import('mongodb');
    
    const client = new MongoClient(uri);
    await client.connect();
    
    const db = client.db(dbName);
    const collection = db.collection(collectionName);
    
    const documents = await collection.find({
      userEdited: true,
      originalText: { $exists: true, $ne: '' },
      editedText: { $exists: true, $ne: '' }
    }).toArray();
    
    await client.close();
    
    const translations: Translation[] = documents.map(doc => ({
      originalText: doc.originalText,
      editedText: doc.editedText
    }));
    
    console.log(`✅ MongoDB에서 ${translations.length}개의 사용자 수정 번역 데이터를 가져왔습니다.`);
    return translations;
    
  } catch (error) {
    console.error('❌ MongoDB 연결 오류:', error);
    console.log('   npm install mongodb 를 먼저 실행하세요.');
    return [];
  }
}


/**
 * DB가 없을 경우 샘플 데이터를 반환합니다.
 * 실제 사용시에는 위의 DB 함수를 사용하세요.
 */
function getSampleData(): Translation[] {
  return [
    {
      originalText: "Cadwell's EMG solutions are designed for comprehensive neuromuscular diagnostics.",
      editedText: 'Cadwell의 EMG 솔루션은 포괄적인 신경근육 진단을 위해 설계되었습니다.'
    },
    {
      originalText: 'Our devices provide accurate and reliable measurements for clinical assessments.',
      editedText: '당사의 장비는 임상 평가를 위한 정확하고 신뢰할 수 있는 측정을 제공합니다.'
    },
    {
      originalText: 'The system integrates seamlessly with existing hospital infrastructure.',
      editedText: '이 시스템은 기존 병원 인프라와 완벽하게 통합됩니다.'
    },
    {
      originalText: 'Advanced filtering algorithms ensure high-quality signal acquisition.',
      editedText: '고급 필터링 알고리즘으로 고품질 신호 획득을 보장합니다.'
    },
    {
      originalText: 'The user interface is designed for efficiency and ease of use.',
      editedText: '사용자 인터페이스는 효율성과 사용 편의성을 위해 설계되었습니다.'
    }
  ];
}


/**
 * OpenAI Fine-tuning Chat 형식으로 변환
 */
function convertToOpenAIFormat(data: Translation[]): OpenAITrainingExample[] {
  return data.map(item => ({
    messages: [
      {
        role: 'system' as const,
        content: SYSTEM_PROMPT
      },
      {
        role: 'user' as const,
        content: item.originalText
      },
      {
        role: 'assistant' as const,
        content: item.editedText
      }
    ]
  }));
}


/**
 * 데이터를 JSONL 파일로 저장
 * 각 줄은 하나의 JSON 객체
 */
function saveToJSONL(data: OpenAITrainingExample[], outputPath: string): void {
  const jsonlContent = data
    .map(item => JSON.stringify(item))
    .join('\n');
  
  fs.writeFileSync(outputPath, jsonlContent, 'utf-8');
  
  console.log(`✅ JSONL 파일이 생성되었습니다: ${outputPath}`);
  console.log(`   총 ${data.length}개의 학습 예제`);
}


/**
 * 생성된 JSONL 파일의 유효성을 검사합니다.
 */
function validateJSONL(filePath: string): boolean {
  try {
    const content = fs.readFileSync(filePath, 'utf-8');
    const lines = content.trim().split('\n');
    
    console.log(`\n📊 JSONL 파일 검증:`);
    console.log(`   - 총 라인 수: ${lines.length}`);
    
    // 처음 3개만 검증
    for (let i = 0; i < Math.min(3, lines.length); i++) {
      const data = JSON.parse(lines[i]) as OpenAITrainingExample;
      
      if (!data.messages || data.messages.length !== 3) {
        console.log(`   ❌ 라인 ${i + 1}: messages 배열이 올바르지 않습니다.`);
        return false;
      }
      
      if (
        data.messages[0].role !== 'system' ||
        data.messages[1].role !== 'user' ||
        data.messages[2].role !== 'assistant'
      ) {
        console.log(`   ❌ 라인 ${i + 1}: role이 올바르지 않습니다.`);
        return false;
      }
      
      if (i === 0) {
        console.log(`\n   ✅ 첫 번째 예제:`);
        console.log(`      User: ${data.messages[1].content.substring(0, 50)}...`);
        console.log(`      Assistant: ${data.messages[2].content.substring(0, 50)}...`);
      }
    }
    
    console.log(`   ✅ JSONL 형식이 올바릅니다!`);
    return true;
    
  } catch (error) {
    console.error(`❌ 파일 검증 실패:`, error);
    return false;
  }
}


/**
 * 메인 실행 함수
 */
async function main() {
  console.log('='.repeat(60));
  console.log('OpenAI Fine-tuning JSONL 데이터 생성기 (TypeScript/Node.js)');
  console.log('='.repeat(60));
  
  // 1. 데이터 가져오기
  let translations: Translation[];
  
  // 옵션 A: SQLite 사용
  // const dbPath = 'path/to/your/database.db';
  // translations = await getEditedTranslationsFromSQLite(dbPath);
  
  // 옵션 B: PostgreSQL 사용
  // translations = await getEditedTranslationsFromPostgreSQL(
  //   'localhost',
  //   5432,
  //   'translation_db',
  //   'postgres',
  //   'your_password'
  // );
  
  // 옵션 C: MongoDB 사용
  // translations = await getEditedTranslationsFromMongoDB(
  //   'mongodb://localhost:27017',
  //   'translation_db',
  //   'translations'
  // );
  
  // 옵션 D: 샘플 데이터 사용 (테스트용)
  console.log('\n⚠️  샘플 데이터를 사용합니다.');
  console.log('   실제 DB를 사용하려면 코드에서 해당 함수를 활성화하세요.\n');
  translations = getSampleData();
  
  if (translations.length === 0) {
    console.log('❌ 데이터가 없습니다. DB 연결을 확인하세요.');
    return;
  }
  
  // 2. OpenAI 형식으로 변환
  console.log(`\n🔄 OpenAI Fine-tuning 형식으로 변환 중...`);
  const formattedData = convertToOpenAIFormat(translations);
  
  // 3. JSONL 파일로 저장
  console.log(`\n💾 JSONL 파일 저장 중...`);
  saveToJSONL(formattedData, OUTPUT_FILE);
  
  // 4. 유효성 검사
  validateJSONL(OUTPUT_FILE);
  
  console.log('\n' + '='.repeat(60));
  console.log('✅ 완료!');
  console.log(`   파일 위치: ${path.resolve(OUTPUT_FILE)}`);
  console.log(`   이 파일을 Google Colab에 업로드하여 Fine-tuning을 진행하세요.`);
  console.log('='.repeat(60));
}


// 스크립트 실행
main().catch(console.error);



