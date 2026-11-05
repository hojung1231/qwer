package expo.modules.bogoimage

import android.graphics.*
import android.net.Uri
import expo.modules.kotlin.modules.Module
import expo.modules.kotlin.modules.ModuleDefinition
import org.json.JSONArray
import java.io.File
import kotlin.math.*

/** Draw directly on source pixels, never on a screenshot of the preview. */
class BogoImageModule : Module() {
  override fun definition() = ModuleDefinition {
    Name("BogoImage")
    AsyncFunction("render") { source: String, json: String, previewWidth: Double ->
      val context = appContext.reactContext ?: error("App context unavailable")
      val input = Uri.parse(source)
      require(input.scheme == "file") { "Local source image required" }
      val options = BitmapFactory.Options().apply { inMutable = true; inPreferredConfig = Bitmap.Config.ARGB_8888 }
      val bitmap = BitmapFactory.decodeFile(input.path, options) ?: error("Cannot decode original photo")
      try {
        val canvas = Canvas(bitmap)
        val scale = bitmap.width / previewWidth.toFloat().coerceAtLeast(1f)
        val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply { strokeJoin = Paint.Join.ROUND; strokeCap = Paint.Cap.ROUND }
        val shapes = JSONArray(json)
        for (i in 0 until shapes.length()) {
          val s = shapes.getJSONObject(i)
          val x1 = s.getDouble("x1").toFloat() * bitmap.width
          val y1 = s.getDouble("y1").toFloat() * bitmap.height
          val x2 = s.getDouble("x2").toFloat() * bitmap.width
          val y2 = s.getDouble("y2").toFloat() * bitmap.height
          val left = min(x1,x2); val top = min(y1,y2)
          val color = Color.parseColor(s.getString("color"))
          paint.color = color; paint.style = Paint.Style.STROKE; paint.strokeWidth = 3f*scale
          val rect = RectF(left, top, max(x1,x2), max(y1,y2))
          when(s.getString("kind")) {
            "circle" -> canvas.drawOval(rect,paint)
            "rectangle" -> canvas.drawRect(rect,paint)
            "arrow" -> {
              canvas.drawLine(x1,y1,x2,y2,paint)
              val angle = atan2(y2-y1,x2-x1); val head=14f*scale
              val path=Path().apply {
                moveTo(x2,y2)
                lineTo(x2-head*cos(angle-.45f),y2-head*sin(angle-.45f))
                lineTo(x2-head*cos(angle+.45f),y2-head*sin(angle+.45f)); close()
              }
              paint.style=Paint.Style.FILL;canvas.drawPath(path,paint)
            }
          }
          val cx=(left+9f*scale).coerceIn(13f*scale,max(13f*scale,bitmap.width-13f*scale))
          val cy=(top-13f*scale).coerceIn(13f*scale,max(13f*scale,bitmap.height-13f*scale))
          paint.style=Paint.Style.FILL;paint.color=Color.WHITE;canvas.drawCircle(cx,cy,11f*scale,paint)
          paint.style=Paint.Style.STROKE;paint.color=color;paint.strokeWidth=2f*scale;canvas.drawCircle(cx,cy,11f*scale,paint)
          paint.style=Paint.Style.FILL;paint.textSize=12f*scale;paint.typeface=Typeface.DEFAULT_BOLD;paint.textAlign=Paint.Align.CENTER
          canvas.drawText((i+1).toString(),cx,cy+4f*scale,paint)
        }
        val output=File(context.cacheDir,"edited-${java.util.UUID.randomUUID()}.jpg")
        output.outputStream().use { require(bitmap.compress(Bitmap.CompressFormat.JPEG,100,it)) }
        Uri.fromFile(output).toString()
      } finally { bitmap.recycle() }
    }
  }
}
