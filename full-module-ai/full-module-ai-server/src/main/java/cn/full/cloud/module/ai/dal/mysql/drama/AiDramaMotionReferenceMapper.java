package cn.full.cloud.module.ai.dal.mysql.drama;

import cn.full.cloud.framework.mybatis.core.mapper.BaseMapperX;
import cn.full.cloud.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.full.cloud.module.ai.dal.dataobject.drama.AiDramaMotionReferenceDO;
import org.apache.ibatis.annotations.Mapper;

import java.util.List;

/**
 * AI 短剧动作参考 Mapper
 *
 * @author 芋道源码
 */
@Mapper
public interface AiDramaMotionReferenceMapper extends BaseMapperX<AiDramaMotionReferenceDO> {

    default List<AiDramaMotionReferenceDO> selectListByProjectId(Long projectId) {
        return selectList(new LambdaQueryWrapperX<AiDramaMotionReferenceDO>()
                .eq(AiDramaMotionReferenceDO::getProjectId, projectId)
                .orderByDesc(AiDramaMotionReferenceDO::getId));
    }

    default int deleteByProjectId(Long projectId) {
        return delete(AiDramaMotionReferenceDO::getProjectId, projectId);
    }

}
