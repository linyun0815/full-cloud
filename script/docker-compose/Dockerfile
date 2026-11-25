FROM eclipse-temurin:25-jre

ARG JAR_FILE
ARG APP_PORT

WORKDIR /app
COPY ${JAR_FILE} app.jar

ENV TZ=Asia/Shanghai JAVA_OPTS="-Xms512m -Xmx512m"
EXPOSE ${APP_PORT}

CMD java ${JAVA_OPTS} -Djava.security.egd=file:/dev/./urandom -jar app.jar
