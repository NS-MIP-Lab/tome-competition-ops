/* =====================================================================
   問題D　エラトステネスのふるい

   このファイルには、左ペインに表示するソースコードと、
   右ペインの設問（Q1〜Q9）が入っています。
   4択問題は pD_quiz.js にあります。

     name   … 書き出しに記録するアルゴリズム名。画面には表示しません
     source … 左ペインに出すソースコード
     steps  … 設問。ブロックの種類は次のとおり
                subhead … 小見出し
                note    … 説明文
                grid    … 表。セルが文字列＝固定表示 / null＝記述欄 /
                          {pre,suf}＝前後の文字つき空欄 / {choice:[…]}＝選択肢
                fill    … 穴埋め文。{b:"キー"}＝空欄、{c:["A","B"]}＝選択肢
                text    … 自由記述欄
                scale   … 5段階の理解度自己評価

   設問の行番号は 9〜11 / 14 / 17〜18 / 19〜21 を前提にしています。
   ソースコードを差し替えるときは行番号の対応も確認してください。
   ===================================================================== */
var PROBLEMS = (typeof PROBLEMS !== "undefined" && PROBLEMS) ? PROBLEMS : {};

PROBLEMS["pD"] = {

  name: "エラトステネスのふるい",

  source: String.raw`#include <stdio.h>
#define MAX 30

int main(void)
{
    int prime[MAX + 1];



    for (int i = 0; i <= MAX; i++) {
        prime[i] = 1;
    }



    prime[0] = prime[1] = 0;

    

    for (int i = 2; i * i <= MAX; i++) {
        if (prime[i] == 1) {
            for (int j = i * i; j <= MAX; j += i) {
                prime[j] = 0;
            }
        }
    }

    return 0;
}`,

  steps: [

    { kind:"intro" },

    /* ------------------------------ Q1 ------------------------------ */
    {
      id:"Q1", title:"Q1　動作例：i = 2 のときの配列更新",
      desc:"処理開始前は、prime[0]とprime[1]が0、prime[2]～prime[30]が1です。22～24行目について、jが12に達するまで追跡してください。記入例の行は採点対象外です。",
      blocks:[
        {
          type:"grid",
          headers:["処理順","j","変更する要素","変更前","変更後","次のj"],
          widths:["14%","12%","24%","16%","16%","18%"],
          rows:[
            {example:true, cells:["記入例","4","prime[4]","1","0","6"]},
            {cells:["1","6",  null,null,null,null]},
            {cells:["2","8",  null,null,null,null]},
            {cells:["3","10", null,null,null,null]},
            {cells:["4","12", null,null,null,null]}
          ]
        },
        {type:"note", text:"上の表をもとに、次の空欄を埋めてください。"},
        {type:"fill", lead:"変更された配列要素：", parts:[
          "prime[", {b:"e1",w:"3.5em"}, "]、prime[", {b:"e2",w:"3.5em"}, "]、prime[", {b:"e3",w:"3.5em"},
          "]、prime[", {b:"e4",w:"3.5em"}, "]、prime[", {b:"e5",w:"3.5em"}, "]"
        ]},
        {type:"fill", lead:"jの変化：", parts:[
          "jは、1回の処理ごとに ", {b:"step",w:"5em"}, " ずつ増える。"
        ]},
        {type:"fill", lead:"iとの関係：", parts:[
          "この例では、jの各値は i = 2 の ", {b:"rel",w:"10em"}, " である。"
        ]}
      ]
    },

    /* ------------------------------ Q2 ------------------------------ */
    {
      id:"Q2", title:"Q2　各 for 文・if 文の具体的な条件",
      desc:"コードに書かれている値や条件式を、そのまま読み取って記入してください。目的の説明はまだ不要です。",
      blocks:[
        {type:"subhead", text:"10～12行目の for 文"},
        {
          type:"grid",
          headers:["確認項目","回答"],
          widths:["44%","56%"],
          rows:[
            {cells:["iの最初の値", null]},
            {cells:["繰り返しを続ける条件", null]},
            {cells:["1回ごとのiの更新", null]},
            {cells:["変更する配列要素", {pre:"prime[", suf:"]", w:"7em"}]},
            {cells:["代入する値", null]}
          ]
        },
        {type:"subhead", text:"20～26行目の外側 for 文と if 文"},
        {
          type:"grid",
          headers:["確認項目","回答"],
          widths:["44%","56%"],
          rows:[
            {cells:["iの最初の値", null]},
            {cells:["繰り返しを続ける条件", null]},
            {cells:["1回ごとのiの更新", null]},
            {cells:["内側 for 文を実行する条件", null]}
          ]
        },
        {type:"subhead", text:"22～24行目の内側 for 文"},
        {
          type:"grid",
          headers:["確認項目","回答"],
          widths:["44%","56%"],
          rows:[
            {cells:["jの最初の値", null]},
            {cells:["繰り返しを続ける条件", null]},
            {cells:["1回ごとのjの更新", null]},
            {cells:["変更する配列要素", {pre:"prime[", suf:"]", w:"7em"}]},
            {cells:["代入する値", null]}
          ]
        },
        {type:"fill", lead:"2つのループの関係：", parts:[
          "外側ループのiの値が、内側ループのjの最初の値 ", {b:"start",w:"7em"},
          " と、1回ごとの増加量 ", {b:"inc",w:"7em"}, " を決める。"
        ]}
      ]
    },

    /* ------------------------------ Q3 ------------------------------ */
    {
      id:"Q3", title:"Q3　配列 prime の範囲と値の変化",
      desc:"コードを確認し、配列 prime の添字の範囲と、各処理で実際に代入される値を記入してください。この設問では、値が素数・合成数のどちらを表すかは答えなくて構いません。",
      blocks:[
        {
          type:"grid",
          headers:["確認項目","回答"],
          widths:["52%","48%"],
          rows:[
            {cells:["MAXに設定されている値", null]},
            {cells:["配列 prime の要素数", null]},
            {cells:["使用できる最小の添字", null]},
            {cells:["使用できる最大の添字", null]},
            {cells:["prime[k]は整数何に対応する要素か", {pre:"整数", suf:"に対応する", w:"6em"}]},
            {cells:["10～12行目で最初に値が代入される要素", {pre:"prime[", suf:"]", w:"6em"}]},
            {cells:["10～12行目で最後に値が代入される要素", {pre:"prime[", suf:"]", w:"6em"}]},
            {cells:["10～12行目で各要素に代入される値", null]},
            {cells:["16行目の処理後の prime[0] の値", null]},
            {cells:["16行目の処理後の prime[1] の値", null]},
            {cells:["16行目の処理によって prime[2]～prime[MAX] の値が変わるか", {choice:["変わる","変わらない"]}]},
            {cells:["22～24行目で値を変更する配列要素", {pre:"prime[", suf:"]", w:"6em"}]},
            {cells:["22～24行目で prime[j] に代入する値", null]},
            {cells:["代入後の prime[j] の値", null]}
          ]
        }
      ]
    },

    /* ------------------------------ Q4 ------------------------------ */
    {
      id:"Q4", title:"Q4　コード範囲ごとの処理内容",
      desc:"処理名を考えるのではなく、指定された行で「何を確認し、どの値を変更するか」を記入してください。各コード範囲について、指定された空欄だけを埋めてください。",
      blocks:[
        {type:"fill", lead:"10～12行目：", parts:[
          "i = ", {b:"a1",w:"5em"}, " から ", {b:"a2",w:"5em"},
          " まで、prime[ i ] に値 ", {b:"a3",w:"5em"}, " を代入する。"
        ]},
        {type:"fill", lead:"16行目：", parts:[
          "prime[ ", {b:"b1",w:"4em"}, " ] と prime[ ", {b:"b2",w:"4em"},
          " ] に値 ", {b:"b3",w:"5em"}, " を代入する。"
        ]},
        {type:"fill", lead:"20～21行目：", parts:[
          "i = ", {b:"c1",w:"5em"}, " から始め、条件 ", {b:"c2",w:"14em"},
          " が成立する間、prime[i] が ", {b:"c3",w:"5em"}, " の場合に内側 for 文を実行する。"
        ]},
        {type:"fill", lead:"22～24行目：", parts:[
          "j = ", {b:"d1",w:"5em"}, " から始め、j が ", {b:"d2",w:"5em"},
          " 以下の間、j に ", {b:"d3",w:"5em"}, " を加えながら、prime[j] に値 ",
          {b:"d4",w:"5em"}, " を代入する。"
        ]},
        {type:"fill", lead:"処理後の状態：", parts:[
          "22～24行目を1回実行すると、prime[ j ] の値は ", {b:"e1",w:"5em"}, " になる。"
        ]}
      ]
    },

    /* ------------------------------ Q5 ------------------------------ */
    {
      id:"Q5", title:"Q5　プログラム全体の仕様",
      desc:"Q1～Q4で記入した内容を使い、文章の空欄を埋めてください。1つの長い文章を自由に作る必要はありません。",
      blocks:[
        {type:"subhead", text:"（1）処理対象と目的"},
        {type:"fill", lead:"処理対象：", parts:[
          "このプログラムは、整数 ", {b:"a1",w:"5em"}, " から ", {b:"a2",w:"5em"}, " までを対象とする。"
        ]},
        {type:"fill", lead:"使用するデータ：", parts:[
          "各整数の状態は、配列 ", {b:"a3",w:"7em"}, " の対応する添字に保持する。"
        ]},
        {type:"fill", lead:"処理目的：", parts:[
          "各整数が ", {b:"a4",w:"20em"}, " であるかを区別できる状態にする。"
        ]},

        {type:"subhead", text:"（2）処理方法"},
        {type:"fill", lead:"初期設定：", parts:[
          "最初に prime の全要素を値 ", {b:"b1",w:"4em"},
          " にし、その後 prime[0] と prime[1] を値 ", {b:"b2",w:"4em"}, " にする。"
        ]},
        {type:"fill", lead:"繰り返し処理：", parts:[
          "prime[i] が ", {b:"b3",w:"4em"}, " の場合、j を ", {b:"b4",w:"5em"},
          " から開始し、i ずつ増やしながら prime[j] を値 ", {b:"b5",w:"4em"}, " に変更する。"
        ]},

        {type:"subhead", text:"（3）処理終了後の状態"},
        {type:"fill", lead:"値1の意味：", parts:[
          "処理終了後、prime[k] が 1 の場合、整数 k は ", {b:"c1",w:"14em"}, " である。"
        ]},
        {type:"fill", lead:"値0の意味：", parts:[
          "処理終了後、prime[k] が 0 の場合、整数 k は ", {b:"c2",w:"14em"}, " である。"
        ]},
        {type:"fill", lead:"0と1の扱い：", parts:[
          "prime[0] と prime[1] が 0 に設定されているのは、整数 0 と 1 が ",
          {b:"c3",w:"18em"}, " ためである。"
        ]},

        {type:"subhead", text:"（4）画面出力"},
        {type:"fill", lead:"出力処理：", parts:[
          "このソースコードには、判定結果を画面へ出力する処理が ",
          {c:["ある","ない"], key:"d1"}, " 。"
        ]}
      ]
    },

    /* ------------------------------ Q9 ------------------------------ */
    {
      id:"Q9", title:"Q9　判断に迷った箇所と確信度",
      desc:"コードから判断できなかった箇所、仕様書への書き方に迷った箇所、または設問の意味が分かりにくかった箇所を記述してください。該当する箇所がない場合は「該当なし」と記述してください。",
      blocks:[
        {type:"text", key:"unsure"},
        {type:"note", text:"このプログラムの処理をどの程度理解できたと思いますか。"},
        {type:"scale", key:"confidence"}
      ]
    },

    { kind:"done" }
  ]

};
